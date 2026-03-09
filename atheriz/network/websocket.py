import asyncio
import json
import threading
from fastapi import WebSocket, WebSocketDisconnect, FastAPI
from .protocol import BaseProtocol
from .connection import BaseConnection
from . import connection_manager
from atheriz.logger import logger
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK
import time

class WebSocketConnection(BaseConnection):
    """
    WebSocket-specific implementation of the BaseConnection.
    """
    def __init__(self, websocket: WebSocket, session_id: str | None = None):
        super().__init__(session_id)
        self.websocket = websocket
        self.client_host = websocket.client.host if websocket.client else "?"

    def send_command(self, cmd: str, *args, **kwargs):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        data = json.dumps([cmd, args, kwargs])
        try:
            if threading.get_ident() == self.thread_id:
                self.loop.create_task(self.websocket.send_text(data))
            else:
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send_text(data), self.loop
                )
        except Exception as e:
            logger.debug(f"[WebSocket] Error sending command: {e}")

    async def _close_websocket(self):
        try:
            await self.websocket.close()
        except Exception:
            pass

    def close(self):
        try:
            if threading.get_ident() == self.thread_id:
                self.loop.create_task(self._close_websocket())
            else:
                asyncio.run_coroutine_threadsafe(self._close_websocket(), self.loop)
        except Exception as e:
            logger.debug(f"[WebSocket] Error closing connection: {e}")


class WebSocketProtocol(BaseProtocol):
    """
    Sets up the FastAPI websocket route.
    """
    @classmethod
    def setup(cls, app: FastAPI):
        import atheriz.settings as settings
        if not getattr(settings, "WEBSOCKET_ENABLED", True):
            return

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            with TEMP_BANNED_LOCK:
                if websocket.client.host in TEMP_BANNED_IPS:
                    if time.time() < TEMP_BANNED_IPS[websocket.client.host]:
                        logger.warning(f"Host {websocket.client.host} in temp ban list has tried to connect.")
                        await websocket.close()
                        return
                    else:
                        del TEMP_BANNED_IPS[websocket.client.host]

            await websocket.accept()
            
            conn_id = connection_manager.generate_connection_id()
            connection = WebSocketConnection(websocket=websocket, session_id=conn_id)
            connection_manager.register_connection(conn_id, connection)

            try:
                while True:
                    raw_message = await websocket.receive_text()
                    connection_manager.handle_command(connection, raw_message)
            except WebSocketDisconnect:
                connection_manager.disconnect(connection)
