"""Issue tests: #12 — concurrent hot-reloads must be serialized.

Two concurrent `reload_game_logic()` calls both iterate `sys.modules` and
`importlib.reload` the same module graph at once; `_reload_lock`
(reloader.py:277-286) serializes them. This test spawns a subprocess (fresh
interpreter) and instruments `importlib.reload` to report the maximum number
of *concurrent threads* inside a reload across a pair of concurrent reloads.

Only distinct threads count as overlap: reloading the command modules
(`commands/loggedin/reload.py`, `shutdown.py`, `rehash.py`) legitimately nests
a same-thread `importlib.reload(server_events)` in their module-level code, so
a plain in-flight counter would report a false overlap of 2.

INTENT: concurrent reload requests must be serialized (max concurrent threads
inside `importlib.reload` == 1).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CHILD = r"""
import sys
import threading
import time

sys.path.insert(0, {repo_root!r})

import atheriz.reloader as R

active = set()
max_overlap = 0
rlock = threading.Lock()
orig_reload = R.importlib.reload


def slow_reload(module):
    global max_overlap
    tid = threading.get_ident()
    with rlock:
        active.add(tid)
        max_overlap = max(max_overlap, len(active))
    time.sleep(0.05)
    try:
        return orig_reload(module)
    finally:
        with rlock:
            active.discard(tid)


R.importlib.reload = slow_reload

barrier = threading.Barrier(2)


def worker():
    barrier.wait()
    t = threading.Thread(target=barrier.reset)
    try:
        R.reload_game_logic()
    except Exception as exc:
        sys.stderr.write(f"AT_ERR {{exc!r}}\n")
    finally:
        t.start()
        t.join()


t1 = threading.Thread(target=worker)
t2 = threading.Thread(target=worker)
t1.start()
t2.start()
t1.join(timeout=180)
t2.join(timeout=180)

print(f"AT_RESULT max_overlap={{max_overlap}}")
"""


def _run_child():
    child = CHILD.format(repo_root=str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
        timeout=200,
    )
    results = dict(re.findall(r"AT_RESULT (\w+)=(\S+)", proc.stdout))
    return proc, results


def test_reloads_are_serialized(global_test_env):
    """INTENT: concurrent reloads never overlap (max concurrent threads inside
    importlib.reload is 1). `_reload_lock` serializes the requests; nested
    same-thread reloads (e.g. a command module's module-level
    importlib.reload(server_events)) must NOT count as overlap."""
    proc, results = _run_child()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    max_overlap = int(results.get("max_overlap", "-1"))
    assert max_overlap <= 1, f"concurrent reloads overlapped {max_overlap} deep"


def test_http_vs_ingame_reload_not_interleaved(global_test_env, tmp_path):
    """INTENT: `5.5` — `hot_reload_endpoint` (`asyncio.Lock` → `threading.Lock`
    across `do_reload` + `_reload_game_logic`) vs `reload_game_logic()` (only
    `threading.Lock`) must not interleave `do_reload`'s `ticker.clear` with
    patching. HTTP holds both locks; in-game holds only threading. `Barrier(2)`
    racing `reload_game_logic` vs `hot_reload_endpoint` must serialize
    (`max_overlap==1`, second gets `already in progress` or waits, never both
    inside `do_reload`/`importlib.reload` at once). Reuses `hot_reload_endpoint`
    + `reloader._reload_lock` ordering `asyncio→threading`."""
    import asyncio
    import threading
    import time
    from unittest.mock import patch

    import atheriz.atheriz as AZ
    import atheriz.reloader as R

    (tmp_path / "admin.token").write_text("real-token")

    active: set[int] = set()
    max_overlap = 0
    overlap_lock = threading.Lock()
    orig_reload = R.importlib.reload
    barrier = threading.Barrier(2, timeout=5)

    def slow_reload(module):
        nonlocal max_overlap
        tid = threading.get_ident()
        with overlap_lock:
            active.add(tid)
            max_overlap = max(max_overlap, len(active))
        time.sleep(0.05)
        try:
            return orig_reload(module)
        finally:
            with overlap_lock:
                active.discard(tid)

    def slow_do_reload(*_a, **_k):
        nonlocal max_overlap
        tid = threading.get_ident()
        with overlap_lock:
            active.add(tid)
            max_overlap = max(max_overlap, len(active))
        time.sleep(0.05)
        try:
            # keep original do_reload semantics minimal: just sleep, no side effects
            return None
        finally:
            with overlap_lock:
                active.discard(tid)

    R.importlib.reload = slow_reload

    results: list[str] = []
    errors: list[str] = []

    class _FakeClient:
        host = "127.0.0.1"

    class _FakeRequest:
        def __init__(self, token: str, host: str = "127.0.0.1"):
            self.headers = {"X-Admin-Token": token}
            self.client = _FakeClient()
            self.client.host = host

    def ingame_worker():
        try:
            barrier.wait(timeout=5)
            res = R.reload_game_logic()
            results.append(res)
        except Exception as exc:
            errors.append(f"ingame: {exc!r}")

    async def http_call():
        return await AZ.hot_reload_endpoint(_FakeRequest(token="real-token"))

    def http_worker():
        try:
            barrier.wait(timeout=5)
            res = asyncio.run(http_call())
            results.append(str(res))
        except Exception as exc:
            errors.append(f"http: {exc!r}")

    with patch.object(AZ, "do_reload", side_effect=slow_do_reload), \
         patch("atheriz.settings.SECRET_PATH", str(tmp_path)):
        t1 = threading.Thread(target=ingame_worker)
        t2 = threading.Thread(target=http_worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

    R.importlib.reload = orig_reload

    assert not errors, f"errors: {errors}"
    assert max_overlap <= 1, f"HTTP vs in-game overlapped {max_overlap} (active={active})"
    # one of them must have been serialized: either HTTP got "already in progress"
    # or in-game did (non-blocking second returns skipping). Never both ran
    # do_reload+reload concurrently.
    assert any("already in progress" in r.lower() for r in results) or len(results) == 2, f"expected serialization, results={results}"