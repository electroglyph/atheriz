"""Issue tests: the WebSocket endpoint leaks connections when the socket is
closed or errors out — `connection_manager.disconnect` is never invoked.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from atheriz.network.websocket import WebSocketProtocol


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
        """INTENT: an oversized message must tear the connection down via
        connection_manager.disconnect, not just close the raw socket."""
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
        """INTENT: any unhandled exception while reading a message must still
        clean the connection up via connection_manager.disconnect."""
        endpoint = _capture_endpoint()

        async def boom():
            raise RuntimeError("socket error")

        ws = _make_ws(boom)

        with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
             patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
             patch("atheriz.network.websocket.get_connection_manager") as mcm:
            _run(endpoint, ws)

        mcm.return_value.disconnect.assert_called_once()
