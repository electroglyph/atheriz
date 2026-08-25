"""Tests for the per-IP connection cap (`settings.MAX_CONNECTIONS_PER_IP`).

The cap is enforced by `ConnectionManager.register_connection`, the single
chokepoint both protocols (websocket and telnet) use after accepting a
connection: a refused connection is closed and never registered.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from atheriz.network.manager import ConnectionManager
from atheriz.tests.fakes import FakeConnection

HOST = "1.2.3.4"


def _conn(host=HOST):
    c = FakeConnection()
    c.client_host = host
    return c


def _cap(value):
    return patch("atheriz.settings.MAX_CONNECTIONS_PER_IP", value)


def test_third_connection_from_same_host_is_refused(global_test_env):
    manager = ConnectionManager()
    with _cap(2):
        assert manager.register_connection("c1", _conn()) is True
        assert manager.register_connection("c2", _conn()) is True
        third = _conn()
        with patch.object(third, "close") as close_spy:
            assert manager.register_connection("c3", third) is False
            close_spy.assert_called_once()
    assert manager.connection_count == 2


def test_connections_from_different_hosts_allowed(global_test_env):
    manager = ConnectionManager()
    with _cap(2):
        assert manager.register_connection("a1", _conn(HOST)) is True
        assert manager.register_connection("a2", _conn(HOST)) is True
        assert manager.register_connection("b1", _conn("9.9.9.9")) is True
    assert manager.connection_count == 3


def test_unknown_host_never_limited(global_test_env):
    manager = ConnectionManager()
    with _cap(2):
        assert manager.register_connection("c0", FakeConnection()) is True
        assert manager.register_connection("c1", FakeConnection()) is True
        third = FakeConnection()
        with patch.object(third, "close") as close_spy:
            assert manager.register_connection("c2", third) is False
            close_spy.assert_called_once()


def test_slot_freed_after_disconnect(global_test_env):
    manager = ConnectionManager()
    with _cap(2):
        c1 = _conn()
        c2 = _conn()
        manager.register_connection("c1", c1)
        manager.register_connection("c2", c2)
        manager.disconnect(c1)
        assert manager.register_connection("c3", _conn()) is True
    assert manager.connection_count == 2


def test_zero_cap_disables_limit(global_test_env):
    manager = ConnectionManager()
    with _cap(0):
        for i in range(3):
            assert manager.register_connection(f"c{i}", _conn()) is True
    assert manager.connection_count == 3


def test_websocket_endpoint_exits_when_registration_refused(global_test_env):
    captured = {}

    def fake_ws(path):
        def decorator(fn):
            captured[path] = fn
            return fn

        return decorator

    app = MagicMock()
    app.websocket.side_effect = fake_ws
    with patch("atheriz.settings.WEBSOCKET_ENABLED", True):
        from atheriz.network.websocket import WebSocketProtocol

        WebSocketProtocol.setup(app)
    endpoint = captured["/ws"]

    ws = MagicMock()
    ws.client = MagicMock()
    ws.client.host = HOST

    async def noop(*a, **kw):
        return None

    ws.accept.side_effect = noop

    async def run():
        await endpoint(ws)

    with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
         patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
         patch("atheriz.network.websocket.get_connection_manager") as mcm:
        mcm.return_value.register_connection.return_value = False
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

    mcm.return_value.handle_command.assert_not_called()
    mcm.return_value.disconnect.assert_not_called()


def test_telnet_shell_exits_when_registration_refused(global_test_env):
    from contextlib import asynccontextmanager

    import atheriz.network.telnet as telnet_mod
    from atheriz.network.telnet import TelnetProtocol

    captured = {}

    class _ServerStub:
        def close(self):
            pass

        async def wait_closed(self):
            return None

    async def _fake_create_server(**kwargs):
        captured["shell"] = kwargs["shell"]
        return _ServerStub()

    app = MagicMock()
    app.router = MagicMock()
    app.router.lifespan_context = None

    with patch("atheriz.settings.TELNET_ENABLED", True), \
         patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake_create_server):
        TelnetProtocol.setup(app)
        installed = app.router.lifespan_context

        async def mount():
            async with installed(app):
                pass

        with patch("atheriz.network.telnet.get_connection_manager") as mcm:
            mcm.return_value.generate_connection_id.return_value = "conn_x"
            mcm.return_value.register_connection.return_value = False

            reader = MagicMock()
            writer = MagicMock()
            writer.get_extra_info.return_value = (HOST, 1234)

            async def run_shell():
                await captured["shell"](reader, writer)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(mount())
                loop.run_until_complete(run_shell())
            finally:
                loop.close()

    mcm.return_value.dispatch.assert_not_called()
