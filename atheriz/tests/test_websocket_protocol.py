"""Tests for atheriz.network.websocket — WebSocketConnection and WebSocketProtocol."""
from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from atheriz.network.websocket import WebSocketConnection, WebSocketProtocol


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
        # Patch the send to capture
        sent = []
        async def fake_send(data):
            sent.append(data)
        ws.send_text.side_effect = fake_send
        # Run on a fake loop
        loop = asyncio.new_event_loop()
        conn.loop = loop
        conn.send_command("text", "hello", k="v")
        # Schedule the task
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
        app.websocket.return_value = lambda f: f  # decorator passthrough
        with patch("atheriz.settings.WEBSOCKET_ENABLED", True):
            WebSocketProtocol.setup(app)
        # websocket decorator was called with /ws
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
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect()

        ws.receive_text.side_effect = fake_receive

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
             patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
             patch("atheriz.network.websocket.connection_manager") as mock_cm:
            async def run():
                await endpoint(ws)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run())
            finally:
                loop.close()

            mock_cm.handle_command.assert_called_once()
            ws.close.assert_not_called()
