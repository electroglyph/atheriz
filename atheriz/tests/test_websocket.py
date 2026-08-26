"""Tests for atheriz.network.websocket — WebSocketConnection, WebSocketProtocol and endpoint disconnect handling."""
from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from atheriz.network.websocket import WebSocketConnection, WebSocketProtocol


def _capture_endpoint():
    captured = {}

    def fake_ws(path):
        def decorator(fn):
            captured[path] = fn
            return fn

        return decorator

    app = MagicMock()
    app.websocket.side_effect = fake_ws
    with patch("atheriz.settings.WEBSOCKET_ENABLED", True):
        WebSocketProtocol.setup(app)
    return captured["/ws"]


def _run(endpoint, ws):
    async def run():
        await endpoint(ws)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


def _make_ws(receive_effect):
    ws = MagicMock()
    ws.client.host = "127.0.0.1"

    async def noop(*a, **kw):
        return None

    ws.accept.side_effect = noop
    ws.close.side_effect = noop
    ws.receive_text.side_effect = receive_effect
    return ws


class TestWebSocketDisconnect:
    def test_oversized_message_disconnects_connection(self, global_test_env):
        endpoint = _capture_endpoint()

        async def oversized():
            return "x" * 100_000

        ws = _make_ws(oversized)

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
              patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
              patch("atheriz.network.websocket.get_connection_manager") as mcm:
            _run(endpoint, ws)

        mcm.return_value.disconnect.assert_called_once()

    def test_receive_error_disconnects_connection(self, global_test_env):
        endpoint = _capture_endpoint()

        async def boom():
            raise RuntimeError("socket error")

        ws = _make_ws(boom)

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
              patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
              patch("atheriz.network.websocket.get_connection_manager") as mcm:
            _run(endpoint, ws)

        mcm.return_value.disconnect.assert_called_once()


class TestWebSocketNone:
    def test_ws_endpoint_tolerates_client_none(self, global_test_env):
        endpoint = _capture_endpoint()

        ws = MagicMock()
        ws.client = None

        async def noop(*a, **kw):
            return None

        ws.accept.side_effect = noop
        ws.close.side_effect = noop

        async def disconnected():
            raise WebSocketDisconnect()

        ws.receive_text.side_effect = disconnected

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
              patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
              patch("atheriz.network.websocket.get_connection_manager") as mcm:
            async def run():
                await endpoint(ws)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run())
            finally:
                loop.close()

        mcm.return_value.disconnect.assert_called_once()


class TestWebSocketConnection:
    def test_init_stores_websocket(self, global_test_env):
        ws = MagicMock()
        ws.client.host = "127.0.0.1"
        conn = WebSocketConnection(websocket=ws)
        assert conn.websocket is ws

    def test_init_stores_client_host(self, global_test_env):
        ws = MagicMock()
        ws.client.host = "10.0.0.1"
        conn = WebSocketConnection(websocket=ws)
        assert conn.client_host == "10.0.0.1"

    def test_init_handles_no_client(self, global_test_env):
        ws = MagicMock()
        ws.client = None
        conn = WebSocketConnection(websocket=ws)
        assert conn.client_host == "?"

    def test_session_id(self, global_test_env):
        ws = MagicMock()
        ws.client = None
        conn = WebSocketConnection(websocket=ws, session_id="abc")
        assert conn.session_id == "abc"


class TestWebSocketConnectionSendCommand:
    def test_serializes_data(self, global_test_env):
        ws = MagicMock()
        ws.client = None
        conn = WebSocketConnection(websocket=ws, session_id="x")
        sent = []
        async def fake_send(data):
            sent.append(data)
        ws.send_text.side_effect = fake_send
        loop = asyncio.new_event_loop()
        conn.loop = loop
        conn.send_command("text", "hello", k="v")
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()
        assert len(sent) == 1
        parsed = json.loads(sent[0])
        assert parsed[0] == "text"
        assert "hello" in parsed[1]
        assert parsed[2] == {"k": "v"}

    def test_serialize_no_args(self, global_test_env):
        ws = MagicMock()
        ws.client = None
        conn = WebSocketConnection(websocket=ws, session_id="x")
        sent = []
        async def fake_send(data):
            sent.append(data)
        ws.send_text.side_effect = fake_send
        loop = asyncio.new_event_loop()
        conn.loop = loop
        conn.send_command("ping")
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()
        assert len(sent) == 1
        parsed = json.loads(sent[0])
        assert parsed[0] == "ping"
        assert parsed[1] == []
        assert parsed[2] == {}


class TestWebSocketProtocolSetup:
    def test_setup_registers_route(self, global_test_env):
        app = MagicMock()
        app.websocket.return_value = lambda f: f
        with patch("atheriz.settings.WEBSOCKET_ENABLED", True):
            WebSocketProtocol.setup(app)
        app.websocket.assert_called_once_with("/ws")

    def test_setup_skipped_when_disabled(self, global_test_env):
        app = MagicMock()
        with patch("atheriz.settings.WEBSOCKET_ENABLED", False):
            WebSocketProtocol.setup(app)
        app.websocket.assert_not_called()


class TestBaseProtocol:
    def test_setup_not_implemented(self, global_test_env):
        from atheriz.network.protocol import BaseProtocol
        with pytest.raises(NotImplementedError):
            BaseProtocol.setup(MagicMock())


class TestWebSocketMessageSize:
    def test_rejects_oversized_message(self, global_test_env):
        captured_fn = {}

        def fake_ws(path):
            def decorator(fn):
                captured_fn[path] = fn
                return fn
            return decorator

        app = MagicMock()
        app.websocket.side_effect = fake_ws
        with patch("atheriz.settings.WEBSOCKET_ENABLED", True):
            WebSocketProtocol.setup(app)

        endpoint = captured_fn["/ws"]
        ws = MagicMock()
        ws.client.host = "127.0.0.1"

        async def noop(*a, **kw):
            return None

        ws.accept.side_effect = noop
        ws.close.side_effect = noop

        async def oversized():
            return "x" * 100_000

        ws.receive_text.side_effect = oversized

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
              patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}):
            async def run():
                await endpoint(ws)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run())
            finally:
                loop.close()

        ws.close.assert_called_once()
        assert ws.close.call_args[1]["code"] == 1009

    def test_accepts_normal_message(self, global_test_env):
        captured_fn = {}

        def fake_ws(path):
            def decorator(fn):
                captured_fn[path] = fn
                return fn
            return decorator

        app = MagicMock()
        app.websocket.side_effect = fake_ws
        with patch("atheriz.settings.WEBSOCKET_ENABLED", True):
            WebSocketProtocol.setup(app)

        endpoint = captured_fn["/ws"]
        ws = MagicMock()
        ws.client.host = "127.0.0.1"

        async def noop(*a, **kw):
            return None

        ws.accept.side_effect = noop
        call_count = 0

        async def fake_receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "hello"
            raise WebSocketDisconnect()

        ws.receive_text.side_effect = fake_receive

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
              patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
              patch("atheriz.network.websocket.get_connection_manager") as mock_get_cm:
            async def run():
                await endpoint(ws)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run())
            finally:
                loop.close()

        mock_get_cm.return_value.handle_command.assert_called_once()
        ws.close.assert_not_called()


class TestWebSocketSendSerialization:
    def test_websocket_sends_have_per_socket_lock(self, global_test_env):
        """INTENT: concurrent send_text must be serialized via per-socket
        asyncio.Lock; otherwise messages interleave/corrupt."""
        ws = MagicMock()
        ws.client.host = "1.1.1.1"
        conn = WebSocketConnection(websocket=ws)
        assert hasattr(conn, "_send_lock"), "WebSocketConnection missing per-socket asyncio.Lock for M-04"
        import asyncio
        assert isinstance(getattr(conn, "_send_lock"), asyncio.Lock)

    def test_websocket_concurrent_send_text_is_serialized(self, global_test_env):
        """INTENT: concurrent send_command must not run send_text concurrently;
        a per-socket lock should serialize them."""
        import time
        ws = MagicMock()
        ws.client.host = "1.1.1.1"
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        conn = WebSocketConnection(websocket=ws, session_id="x")
        conn.loop = loop
        active = 0
        max_active = 0
        alock = threading.Lock()

        async def fake_send(data):
            nonlocal active, max_active
            with alock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.04)
            with alock:
                active -= 1

        ws.send_text.side_effect = fake_send
        threads = [threading.Thread(target=lambda: conn.send_command("text", "hi")) for _ in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        time.sleep(0.5)
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=2)
        loop.close()
        assert max_active <= 1, f"concurrent send_text not serialized: max_active={max_active}"
