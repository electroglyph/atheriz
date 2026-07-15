"""Tests for atheriz.network.manager — ConnectionManager orchestration."""
from __future__ import annotations

import json
import threading
import _thread
from unittest.mock import MagicMock, patch

import pytest

import atheriz.network.manager as mgr_module
from atheriz.network.manager import ConnectionManager
from atheriz.tests.fakes import FakeConnection


@pytest.fixture
def manager(global_test_env):
    """Create a ConnectionManager with InputFuncs handlers replaced by no-ops."""
    # Reset the singleton so we get a fresh one
    mgr_module._CONNECTION_MANAGER = None
    # Patch InputFuncs so we don't trigger real handlers
    with patch("atheriz.inputfuncs.InputFuncs") as mock_if:
        mock_if.return_value.get_handlers.return_value = {}
        mgr = ConnectionManager()
    yield mgr
    mgr_module._CONNECTION_MANAGER = None


class TestInit:
    def test_init_creates_empty_state(self, manager):
        assert manager._connections == {}
        assert manager._message_handlers == {}
        assert manager._connection_counter == 0

    def test_init_lock_is_rlock(self, manager):
        assert isinstance(manager._lock, _thread.RLock)

    def test_init_registers_handlers_from_inputfuncs(self, global_test_env):
        mgr_module._CONNECTION_MANAGER = None
        with patch("atheriz.inputfuncs.InputFuncs") as mock_if:
            mock_if.return_value.get_handlers.return_value = {"text": lambda c, a, k: None}
            mgr = ConnectionManager()
        assert "text" in mgr._message_handlers
        mgr_module._CONNECTION_MANAGER = None


class TestGenerateConnectionId:
    def test_first_id(self, manager):
        cid = manager.generate_connection_id()
        assert cid == "conn_1"

    def test_increments(self, manager):
        cid1 = manager.generate_connection_id()
        cid2 = manager.generate_connection_id()
        cid3 = manager.generate_connection_id()
        assert cid1 == "conn_1"
        assert cid2 == "conn_2"
        assert cid3 == "conn_3"

    def test_unique(self, manager):
        ids = {manager.generate_connection_id() for _ in range(20)}
        assert len(ids) == 20


class TestRegisterConnection:
    def test_registers(self, manager):
        c = FakeConnection()
        manager.register_connection("c1", c)
        assert manager._connections["c1"] is c

    def test_increments_count(self, manager):
        assert manager.connection_count == 0
        manager.register_connection("c1", FakeConnection())
        assert manager.connection_count == 1
        manager.register_connection("c2", FakeConnection())
        assert manager.connection_count == 2

    def test_overwrites_existing(self, manager):
        c1 = FakeConnection()
        c2 = FakeConnection()
        manager.register_connection("c1", c1)
        manager.register_connection("c1", c2)
        assert manager._connections["c1"] is c2
        assert manager.connection_count == 1


class TestDisconnect:
    def test_removes_connection(self, manager):
        c = FakeConnection()
        manager.register_connection("c1", c)
        manager.disconnect(c)
        assert "c1" not in manager._connections

    def test_calls_session_at_disconnect(self, manager):
        c = FakeConnection()
        manager.register_connection("c1", c)
        c.session.at_disconnect = MagicMock()
        manager.disconnect(c)
        c.session.at_disconnect.assert_called_once()

    def test_decrements_count(self, manager):
        c1 = FakeConnection()
        c2 = FakeConnection()
        manager.register_connection("c1", c1)
        manager.register_connection("c2", c2)
        assert manager.connection_count == 2
        manager.disconnect(c1)
        assert manager.connection_count == 1

    def test_unregistered_connection_noop(self, manager):
        c = FakeConnection()
        # No error if not registered
        manager.disconnect(c)
        assert manager.connection_count == 0

    def test_no_session(self, manager):
        c = FakeConnection()
        c.session = None
        manager.register_connection("c1", c)
        # Should not raise
        manager.disconnect(c)


class TestGetAllConnections:
    def test_empty(self, manager):
        assert manager.get_all_connections() == []

    def test_returns_all(self, manager):
        c1 = FakeConnection()
        c2 = FakeConnection()
        manager.register_connection("c1", c1)
        manager.register_connection("c2", c2)
        conns = manager.get_all_connections()
        assert set(conns) == {c1, c2}

    def test_returns_copy(self, manager):
        c1 = FakeConnection()
        manager.register_connection("c1", c1)
        list1 = manager.get_all_connections()
        list1.clear()
        # Original should be unchanged
        assert manager.connection_count == 1


class TestBroadcast:
    def test_broadcasts_to_all(self, manager):
        c1 = FakeConnection()
        c2 = FakeConnection()
        manager.register_connection("c1", c1)
        manager.register_connection("c2", c2)
        manager.broadcast("hello")
        assert len(c1.sent) == 1
        assert len(c2.sent) == 1

    def test_broadcast_handles_per_connection_error(self, manager):
        c1 = FakeConnection()
        c2 = FakeConnection()
        # Make c1.msg raise
        def boom(*a, **k):
            raise RuntimeError("boom")
        c1.msg = boom
        manager.register_connection("c1", c1)
        manager.register_connection("c2", c2)
        # Should not raise
        manager.broadcast("hi")
        # c2 still got the message
        assert len(c2.sent) == 1

    def test_broadcast_to_empty(self, manager):
        # Should not raise
        manager.broadcast("hi")


class TestRegisterHandler:
    def test_registers(self, manager):
        handler = MagicMock()
        manager.register_handler("foo", handler)
        assert manager._message_handlers["foo"] is handler

    def test_overwrites(self, manager):
        h1 = MagicMock()
        h2 = MagicMock()
        manager.register_handler("foo", h1)
        manager.register_handler("foo", h2)
        assert manager._message_handlers["foo"] is h2


class TestHandleCommand:
    def test_dispatches_to_handler(self, manager):
        handler = MagicMock()
        manager.register_handler("text", handler)
        c = FakeConnection()
        manager.handle_command(c, json.dumps(["text", ["hello"], {}]))
        handler.assert_called_once_with(c, ["hello"], {})

    def test_invalid_json_doesnt_raise(self, manager):
        c = FakeConnection()
        manager.handle_command(c, "not json")  # should not raise

    def test_non_list_data_ignored(self, manager):
        c = FakeConnection()
        handler = MagicMock()
        manager.register_handler("text", handler)
        manager.handle_command(c, json.dumps("not a list"))
        handler.assert_not_called()

    def test_empty_list_ignored(self, manager):
        c = FakeConnection()
        handler = MagicMock()
        manager.register_handler("text", handler)
        manager.handle_command(c, json.dumps([]))
        handler.assert_not_called()

    def test_no_args_kwargs(self, manager):
        handler = MagicMock()
        manager.register_handler("text", handler)
        c = FakeConnection()
        manager.handle_command(c, json.dumps(["text"]))
        handler.assert_called_once_with(c, [], {})

    def test_no_kwargs(self, manager):
        handler = MagicMock()
        manager.register_handler("text", handler)
        c = FakeConnection()
        manager.handle_command(c, json.dumps(["text", ["x"]]))
        handler.assert_called_once_with(c, ["x"], {})

    def test_unknown_cmd_silent(self, manager):
        # INTENT: unknown commands are silently ignored
        c = FakeConnection()
        manager.handle_command(c, json.dumps(["unknown", [], {}]))
        # No exception

    def test_dispatch_error_caught(self, manager):
        # INTENT: errors in handler don't crash the manager
        def bad_handler(*a, **k):
            raise RuntimeError("boom")
        manager.register_handler("text", bad_handler)
        c = FakeConnection()
        manager.handle_command(c, json.dumps(["text"]))  # should not raise


class TestDispatch:
    def test_routes_to_handler(self, manager):
        handler = MagicMock()
        manager.register_handler("text", handler)
        c = FakeConnection()
        manager.dispatch(c, "text", ["a"], {"k": "v"})
        handler.assert_called_once_with(c, ["a"], {"k": "v"})

    def test_unknown_cmd_silent(self, manager):
        c = FakeConnection()
        manager.dispatch(c, "unknown", [], {})  # should not raise

    @patch("atheriz.network.manager.logger")
    def test_unknown_cmd_logged(self, mock_logger, manager):
        c = FakeConnection()
        manager.dispatch(c, "foobar", [], {})
        mock_logger.debug.assert_called_once()
        assert "foobar" in mock_logger.debug.call_args[0][0]


class TestThreadSafety:
    def test_concurrent_register(self, manager):
        errors = []

        def worker(i):
            try:
                c = FakeConnection()
                manager.register_connection(f"c{i}", c)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert manager.connection_count == 20

    def test_concurrent_id_generation(self, manager):
        ids = []
        lock = threading.Lock()

        def worker():
            for _ in range(50):
                cid = manager.generate_connection_id()
                with lock:
                    ids.append(cid)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All IDs unique
        assert len(ids) == len(set(ids))
        assert len(ids) == 200
