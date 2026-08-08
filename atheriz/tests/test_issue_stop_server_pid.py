"""Issue tests: #25 — `stop_server()` trusts the PID file and terminates that
PID even when the grace shutdown handshake fails (the PID may belong to some
unrelated process).

INTENT: `stop_server()` must ONLY terminate a process it can positively verify
owns the server (e.g. graceful-shutdown succeeded, or the port handshake
confirms it). Terminating an unverified stale PID must not happen, and the PID
file must not be cleaned up for a still-live-but-unverified process.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from atheriz import settings


def test_stop_server_does_not_terminate_unverified_pid(global_test_env, monkeypatch):
    import atheriz.atheriz as az

    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    pid_file.write_text("12345")

    # Graceful handshake fails: the server could not be reached.
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)

    proc_stub = MagicMock()
    proc_stub.terminate.return_value = None
    proc_stub.wait.return_value = None
    proc_stub.is_running.return_value = True

    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = proc_stub
    fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
    fake_psutil.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    fake_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake_psutil.net_connections.return_value = []

    # `stop_server` imports psutil inside the function scope, so it resolves
    # from sys.modules.
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    az.stop_server()

    proc_stub.terminate.assert_not_called()
    assert pid_file.exists(), "pid file must not be cleaned up for an unverified process"