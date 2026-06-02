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
