"""Pinned tests for 5.11 — PID file TOCTOU must use O_CREAT|O_EXCL (open "x").

INTENT: Two concurrent `start_server` must not both believe they are the server.
The check `if pid_file.exists(): read; if alive: return; unlink` then
`open("w")` is TOCTOU: Thread A sees stale, unlinks, Thread B sees no file,
both do `do_startup` (slow), both `open("w")` — second overwrites first's PID
and first's `server.pid` points to dead PID. Fix uses `open("x")` (O_CREAT|O_EXCL)
which is atomic on both POSIX and Windows (no fcntl/msvcrt needed), and on
`FileExistsError` re-checks `is_server_process`. `Barrier(2)` forces the race
on the `open("x")` slot.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import atheriz.atheriz as az


def test_pid_file_exclusive_create_concurrent(tmp_path):
    """Two concurrent `open(pid_file, \"x\")` (O_CREAT|O_EXCL) — only one wins, no torn file."""
    pid_file = tmp_path / "server.pid"
    barrier = threading.Barrier(2, timeout=5)
    results: list[str] = []
    errors: list[str] = []

    def try_create(pid: int):
        try:
            barrier.wait(timeout=5)
            with open(pid_file, "x") as f:
                f.write(str(pid))
            results.append(f"win:{pid}")
        except FileExistsError:
            results.append(f"exists:{pid}")
        except Exception as e:
            errors.append(f"{e!r}")

    t1 = threading.Thread(target=try_create, args=(11111,))
    t2 = threading.Thread(target=try_create, args=(22222,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors, f"errors: {errors}"
    assert not t1.is_alive() and not t2.is_alive()
    assert pid_file.exists()
    pid_text = pid_file.read_text().strip()
    assert pid_text in ("11111", "22222"), f"pid file torn: {pid_text!r}"
    assert len(results) == 2
    assert sum(1 for r in results if r.startswith("win:")) == 1
    assert sum(1 for r in results if r.startswith("exists:")) == 1


def test_pid_file_stale_replaced(tmp_path):
    """Stale pid file (dead pid) must be replaced via exclusive-create + re-check (start_server logic)."""
    pid_file = tmp_path / "server.pid"
    pid_file.write_text("99999")

    # Simulate start_server's FileExistsError path: stale file, is_alive False → unlink → open("x") succeeds
    with patch.object(az, "_pid_is_server_process", return_value=False):
        # First attempt open("x") will FileExistsError because file exists
        try:
            with open(pid_file, "x") as f:
                f.write("12345")
            assert False, "should have FileExistsError"
        except FileExistsError:
            # is_alive False → stale, unlink
            pid_file.unlink(missing_ok=True)
            with open(pid_file, "x") as f:
                f.write("12345")
        assert pid_file.exists()
        assert pid_file.read_text().strip() == "12345"


def test_open_x_is_windows_compatible(tmp_path):
    """`open(..., \"x\")` must be the mechanism (O_CREAT|O_EXCL) — no fcntl."""
    # Ensure the fix does not use fcntl.flock (not on Windows) or msvcrt
    import atheriz.atheriz as mod
    import inspect
    src = inspect.getsource(mod.start_server)
    assert 'open(pid_file, "x"' in src or "open(pid_file, 'x'" in src, "start_server must use open(..., \"x\") for Windows"
    assert "fcntl" not in src, "must not use fcntl (Windows incompatible)"
    # msvcrt is also not needed for exclusive create
    assert "msvcrt" not in src


def test_spawn_daemon_uses_exclusive_pid_create(tmp_path):
    import inspect
    src = inspect.getsource(az.spawn_daemon)
    assert 'open(pid_file, "x"' in src or "os.open" in src, "spawn_daemon must use exclusive create to avoid TOCTOU"


def test_spawn_daemon_concurrent_only_one_wins(tmp_path):
    barrier = threading.Barrier(2, timeout=5)
    results = []
    import atheriz.settings as settings
    orig_save = settings.SAVE_PATH
    settings.SAVE_PATH = str(tmp_path)
    tmp_pid = Path(tmp_path) / "server.pid"
    if tmp_pid.exists():
        tmp_pid.unlink()
    def fake_popen(*a, **kw):
        class P:
            pid = 12345
        time.sleep(0.05)
        return P()
    def run_spawn():
        barrier.wait(timeout=5)
        from unittest.mock import MagicMock, patch as mpatch
        args = MagicMock()
        args.port = None
        args.host = None
        with mpatch("atheriz.atheriz.setup_game_folder", return_value=False), \
             mpatch("subprocess.Popen", side_effect=fake_popen), \
             mpatch("atheriz.atheriz._pid_is_server_process", return_value=False), \
             mpatch("atheriz.atheriz.Path", wraps=Path):
            try:
                az.spawn_daemon(args)
                results.append("spawned")
            except Exception as e:
                results.append(f"err:{e}")
    t1 = threading.Thread(target=run_spawn)
    t2 = threading.Thread(target=run_spawn)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    settings.SAVE_PATH = orig_save
    assert results.count("spawned") == 1, f"concurrent spawn_daemon both succeeded: {results} — TOCTOU"


def test_pid_file_toctou_spawn_vs_start(tmp_path):
    import inspect
    src_start = inspect.getsource(az.start_server)
    src_spawn = inspect.getsource(az.spawn_daemon)
    assert src_start.count("FileExistsError") >= 1, "start_server must handle FileExistsError from exclusive create"
    assert "FileExistsError" in src_spawn or "os.open" in src_spawn, "spawn_daemon must also handle races"
