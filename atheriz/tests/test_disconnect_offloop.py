"""Regression tests for issue #3: session teardown must not run on the
network event loop.

manager.disconnect() used to call session.at_disconnect() synchronously from
the protocol endpoints' finally blocks — i.e., on the asyncio loop thread.
That chain does puppet unwinding, channel announcements, and (with
AUTOSAVE_PLAYERS_ON_DISCONNECT) a full dill + SQLite checkpoint inline on the
loop, stalling all network I/O and racing game workers. The fix dispatches
teardown onto the game threadpool, deferring with a short delay when the pool
is stopped or full (never inline on the calling thread).
"""

from __future__ import annotations

import threading
import time

import pytest

import atheriz.network.manager as mgr_module
from atheriz.network.manager import ConnectionManager
from atheriz.tests.fakes import FakeConnection


@pytest.fixture
def manager(global_test_env):
    mgr_module._CONNECTION_MANAGER = None
    from unittest.mock import patch

    with patch("atheriz.inputfuncs.InputFuncs") as mock_if:
        mock_if.return_value.get_handlers.return_value = {}
        mgr = ConnectionManager()
    yield mgr
    mgr_module._CONNECTION_MANAGER = None


def _wait(cond, timeout=2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


class _RecordingSession:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.threads: list[threading.Thread] = []
        self.calls = 0
        self.ran = threading.Event()

    def at_disconnect(self):
        self.calls += 1
        self.threads.append(threading.current_thread())
        if self.delay:
            time.sleep(self.delay)
        self.ran.set()


def test_teardown_runs_off_the_calling_thread(manager):
    """INTENT: disconnect() itself must not run at_disconnect; the teardown is
    dispatched to a threadpool worker."""
    c = FakeConnection(session=_RecordingSession())
    manager.register_connection("c1", c)

    manager.disconnect(c)

    assert c.session.ran.wait(2.0)
    assert c.session.calls == 1
    assert c.session.threads[0] is not threading.current_thread()
    assert c.session.threads[0] in [t for t in manager.atp.threads[1:]]


def test_disconnect_does_not_block_on_slow_teardown(manager):
    """INTENT: disconnect() returns immediately even while teardown (e.g. an
    autosave) is still running; completion happens asynchronously."""
    c = FakeConnection(session=_RecordingSession(delay=0.5))
    manager.register_connection("c1", c)

    start = time.monotonic()
    manager.disconnect(c)
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
    assert c.session.ran.wait(2.0)


def test_deferred_retry_when_pool_rejects(manager, monkeypatch):
    """INTENT: when the threadpool rejects the task (queue full / stopped),
    teardown is deferred via a delayed re-queue — never run inline on the
    calling (event loop) thread and never silently dropped."""
    monkeypatch.setattr(manager.atp, "add_task", lambda *a, **k: False)
    delayed = []
    monkeypatch.setattr(
        manager.atp, "delay", lambda *a, **k: delayed.append((a, k))
    )
    c = FakeConnection(session=_RecordingSession())
    manager.register_connection("c1", c)

    manager.disconnect(c)

    assert c.session.calls == 0, "teardown must not run inline on disconnect"
    assert len(delayed) == 1, "rejected teardown must be deferred for retry"
    (d_args, _) = delayed[0]
    assert d_args[1] == manager._do_session_disconnect
    assert d_args[2] is c.session


def test_teardown_runs_exactly_once_across_double_disconnect(manager):
    """INTENT: the second disconnect() finds no registered connection and
    cannot schedule a second teardown."""
    c = FakeConnection(session=_RecordingSession())
    manager.register_connection("c1", c)

    manager.disconnect(c)
    manager.disconnect(c)

    assert c.session.ran.wait(2.0)
    time.sleep(0.1)
    assert c.session.calls == 1


def test_no_session_disconnect_still_closes(manager):
    """INTENT: connections without a session skip teardown cleanly."""
    c = FakeConnection()
    c.session = None
    manager.register_connection("c1", c)

    manager.disconnect(c)

    assert "c1" not in manager._connections


class TestPoolFullDefersTeardown:
    def test_pool_full_disconnect_defers_teardown_off_loop(
        self, global_test_env, manager, monkeypatch
    ):
        """INTENT: when the pool is full, teardown must be deferred/retried off
        the calling thread — never executed synchronously inside disconnect."""
        monkeypatch.setattr(manager.atp, "add_task", lambda *a, **k: False)
        session = _RecordingSession()
        connection = FakeConnection(session=session)
        manager.register_connection("c1", connection)

        manager.disconnect(connection)

        assert session.calls == 0
