"""Issue tests: `call_soon_threadsafe` on a closed loop aborted disconnect
cleanup.

Session.at_disconnect() cancelled a pending input future via
future.get_loop().call_soon_threadsafe(future.cancel); when the pool loop was
already closed (shutdown / restart singleton swap) that raised RuntimeError,
escaping into ConnectionManager.disconnect and skipping connection.close()
and the rest of teardown. The fix makes the cancel best-effort inside Session;
the manager side already guards teardown and close independently (issue #3).
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

import atheriz.network.manager as mgr_module
from atheriz.network.manager import ConnectionManager
from atheriz.objects.session import Session
from atheriz.tests.fakes import FakeConnection


def _wait(cond, timeout=2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


class TestClosedLoopFutureCancel:
    def test_closed_loop_does_not_abort_teardown(self, global_test_env):
        """INTENT: at_disconnect must complete puppet/account teardown even
        when the future's loop is already closed."""
        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        loop.close()

        s = Session(connection=None)
        s.input_future = fut
        s.conn_time = time.time() - 10.0
        puppet = object.__new__(object)
        from atheriz.objects.base_obj import Object

        puppet = Object.create(None, "Puppeted")
        s.puppet = puppet
        puppet.session = s

        s.at_disconnect()

        assert puppet.session is None
        assert s.puppet_stack == []

    def test_live_loop_still_cancels_prompt(self, global_test_env):
        """INTENT: the normal path is unchanged — a pending prompt future is
        cancelled when its loop is alive."""
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        try:
            s = Session(connection=None)

            ready = threading.Event()
            holder: dict = {}

            def _make_future():
                holder["fut"] = loop.create_future()
                ready.set()

            loop.call_soon_threadsafe(_make_future)
            assert ready.wait(2)
            fut = holder["fut"]
            s.input_future = fut

            s.at_disconnect()

            assert _wait(fut.done)
            assert fut.cancelled()
        finally:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
            t.join(timeout=2)
            loop.close()


@pytest.fixture
def manager(global_test_env):
    mgr_module._CONNECTION_MANAGER = None
    from unittest.mock import patch

    with patch("atheriz.inputfuncs.InputFuncs") as mock_if:
        mock_if.return_value.get_handlers.return_value = {}
        mgr = ConnectionManager()
    yield mgr
    mgr_module._CONNECTION_MANAGER = None


class TestManagerRobustness:
    def test_failing_teardown_still_closes(self, manager, monkeypatch):
        """INTENT: a session whose at_disconnect raises must not skip socket
        close or registry removal."""
        c = FakeConnection(session=None)
        c.session = type("Boom", (), {"at_disconnect": lambda self: 1 / 0})()
        closed = []
        c.close = lambda: closed.append(True)

        manager.register_connection("c1", c)
        monkeypatch.setattr(manager.atp, "add_task", lambda *a, **k: False)

        manager.disconnect(c)

        assert closed == [True]
        assert manager.connection_count == 0
