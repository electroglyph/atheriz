"""Issue tests: #26 — the `/ws` endpoint reads `websocket.client.host`
(websocket.py:86) without a None guard; a connection whose `client` attribute
is None crashes the handler (compare the guard in WebSocketConnection).__init__).

INTENT: the ban check must tolerate `websocket.client is None`.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from fastapi import WebSocketDisconnect

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


def test_ws_endpoint_tolerates_client_none(global_test_env):
    """INTENT: a websocket whose `client` is None must not raise. Today
    `websocket.client.host` raises AttributeError -> the endpoint crashes."""
    endpoint = _capture_endpoint()

    ws = MagicMock()
    ws.client = None  # No client address info available

    async def noop(*a, **kw):
        return None

    ws.accept.side_effect = noop
    ws.close.side_effect = noop

    async def disconnected():
        raise WebSocketDisconnect()

    ws.receive_text.side_effect = disconnected

    with patch("atheriz.network.websocket.TEMP_BANNED_LOCK"), \
         patch("atheriz.network.websocket.TEMP_BANNED_IPS", {}), \
         patch("atheriz.network.websocket.connection_manager") as mcm:
        async def run():
            await endpoint(ws)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

    mcm.disconnect.assert_called_once()