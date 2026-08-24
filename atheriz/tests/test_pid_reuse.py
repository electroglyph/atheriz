"""Issue tests: `start_server()`'s stale-PID check trusted `psutil.pid_exists`
alone. If the OS reused the dead server's PID for an unrelated process, boot
refused with "Server is already running" until the pid file was removed by
hand.

INTENT: a recorded PID only blocks boot when the live process looks like a
python/atheriz process (and is not a zombie); anything else is stale.
"""
from __future__ import annotations

import os

import psutil
import pytest

from atheriz.atheriz import _pid_is_server_process


def _non_python_pid() -> int | None:
    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info["name"] or "").lower()
        if not name.startswith(("python", "atheriz")):
            return proc.info["pid"]
    return None


class TestPidIsServerProcess:
    def test_accepts_current_python_process(self):
        assert _pid_is_server_process(os.getpid()) is True

    def test_rejects_nonexistent_pid(self):
        assert _pid_is_server_process(2**31) is False

    def test_rejects_live_non_python_pid(self):
        """INTENT: PID reuse by an unrelated process must not look like the
        server (the old pid_exists-only check did)."""
        pid = _non_python_pid()
        if pid is None:
            pytest.skip("no non-python process found")
        assert _pid_is_server_process(pid) is False
