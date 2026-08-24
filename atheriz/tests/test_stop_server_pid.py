"""Issue tests: #25 — `stop_server()` trusts the PID file and terminates that
PID even when the grace shutdown handshake fails (the PID may belong to some
unrelated process).

INTENT: `stop_server()` must ONLY terminate a process it can positively verify
owns the server (graceful-shutdown succeeded, or the process is listening on
the webserver port). Terminating an unverified stale PID must not happen, and
the PID file must not be cleaned up for a still-live-but-unverified process;
the file is removed only for a verifiably dead PID or after a verified stop.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
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

    fake_psutil = _fake_psutil(proc_stub, [])

    # `stop_server` imports psutil inside the function scope, so it resolves
    # from sys.modules.
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    az.stop_server()

    proc_stub.terminate.assert_not_called()
    assert pid_file.exists(), "pid file must not be cleaned up for an unverified process"


class _NoSuchProcess(Exception):
    def __init__(self, pid=None, name=None):
        super().__init__(f"Process {pid} no longer exists ({name})")


class _AccessDenied(Exception):
    pass


class _TimeoutExpired(Exception):
    pass


class _ZombieProcess(Exception):
    pass


def _fake_psutil(proc_stub, connections, no_such_process=False):
    fake_psutil = MagicMock()
    fake_psutil.NoSuchProcess = _NoSuchProcess
    fake_psutil.AccessDenied = _AccessDenied
    fake_psutil.TimeoutExpired = _TimeoutExpired
    fake_psutil.ZombieProcess = _ZombieProcess
    if no_such_process:
        fake_psutil.Process.side_effect = lambda pid: (_ for _ in ()).throw(
            _NoSuchProcess(pid=pid)
        )
    else:
        fake_psutil.Process.return_value = proc_stub
    fake_psutil.net_connections.return_value = connections or []
    return fake_psutil


def _install_fake_psutil(monkeypatch, fake_psutil):
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    return fake_psutil


def test_stop_server_removes_stale_pid_file(global_test_env, monkeypatch):
    """INTENT: a PID that no longer exists is stale; the file is cleaned up
    and nothing is terminated."""
    import atheriz.atheriz as az

    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    pid_file.write_text("12345")

    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)

    proc_stub = MagicMock()
    proc_stub.terminate.return_value = None
    fake_psutil = _fake_psutil(proc_stub, [], no_such_process=True)
    _install_fake_psutil(monkeypatch, fake_psutil)

    az.stop_server()

    proc_stub.terminate.assert_not_called()
    assert not pid_file.exists(), "stale pid file must be removed"


def test_stop_server_terminates_verified_listener(global_test_env, monkeypatch):
    """INTENT: a PID listening on the webserver port is verified; it is
    terminated and the pid file is removed once it is gone."""
    import atheriz.atheriz as az

    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    pid_file.write_text("12345")

    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)

    proc_stub = MagicMock()
    proc_stub.pid = 12345
    proc_stub.name.return_value = "python"
    proc_stub.terminate.return_value = None
    proc_stub.wait.return_value = None
    proc_stub.is_running.return_value = False

    listener = SimpleNamespace(
        pid=12345,
        status="LISTEN",
        laddr=SimpleNamespace(port=settings.WEBSERVER_PORT),
    )
    fake_psutil = _fake_psutil(proc_stub, connections=[listener])
    _install_fake_psutil(monkeypatch, fake_psutil)

    az.stop_server()

    proc_stub.terminate.assert_called_once()
    assert not pid_file.exists(), "pid file must be removed after a verified stop"


def test_stop_server_keeps_pid_file_when_scan_finds_nothing(global_test_env, monkeypatch):
    """INTENT: nothing verified -> nothing is cleaned up; an unusable pid file
    (and an unverified PID entry) must survive a fruitless scan."""
    import atheriz.atheriz as az

    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    pid_file.write_text("not-a-pid")

    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)

    proc_stub = MagicMock()
    proc_stub.terminate.return_value = None
    fake_stub = _fake_psutil(proc_stub, connections=[])
    _install_fake_psutil(monkeypatch, fake_stub)

    az.stop_server()

    proc_stub.terminate.assert_not_called()
    assert pid_file.exists(), "pid file must not be cleaned up when nothing was verified"