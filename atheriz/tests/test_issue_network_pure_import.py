"""Issue tests: #21 — `import atheriz.network` has an import side effect: it
instantiates a `ConnectionManager` (network/__init__.py:9) which immediately
spawns the full async threadpool (THREADPOOL_LIMIT worker threads), leaking
threads in any non-server process that merely imports the network package
(docs generator, tests, reloaders).

INTENT: importing `atheriz.network` must not start worker threads.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CHILD = r"""
import sys
import threading

sys.path.insert(0, {repo_root!r})

before = [t for t in threading.enumerate() if t.is_alive()]

from atheriz import network  # noqa: E402  (importing the whole package)

after = [t for t in threading.enumerate() if t.is_alive()]

# The import-related thread we care about: worker threads spawned as a side
# effect of the module import itself.
new_threads = len(after) - len(before)
print(f"AT_RESULT new_threads={{new_threads}}")
"""


def test_network_import_starts_no_threads(global_test_env):
    """INTENT: importing `atheriz.network` must leave the thread count
    unchanged. Today the import-time ConnectionManager starts the threadpool,
    so `new_threads` >= THREADPOOL_LIMIT -> FAIL."""
    child = CHILD.format(repo_root=repr(str(REPO_ROOT)))
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    results = [line for line in proc.stdout.splitlines() if line.startswith("AT_RESULT")]
    assert results, f"no AT_RESULT line in child output: {proc.stdout!r}"
    new_threads = int(results[0].split("=")[1])
    assert new_threads <= 0, f"network import spawned {new_threads} working threads"