from __future__ import annotations
import asyncio
import concurrent.futures
import json
import threading
from fastapi import WebSocket, WebSocketDisconnect, FastAPI
from .protocol import BaseProtocol
from .connection import BaseConnection
from atheriz.globals.get import get_connection_manager
from atheriz.logger import logger
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK, is_ip_banned
import time
import atheriz.settings as settings

_oversize_lock = threading.Lock()
_oversize_last: dict[str, float] = {}
_OVERSIZE_WINDOW = 5.0


def _should_log_oversize(host: str) -> bool:
    now = time.monotonic()
    with _oversize_lock:
        last = _oversize_last.get(host, 0)
        if now - last < _OVERSIZE_WINDOW:
            return False
        _oversize_last[host] = now
        return True

class WebSocketConnection(BaseConnection):
    """
    WebSocket-specific implementation of the BaseConnection.
    """
    def __init__(self, websocket: WebSocket, session_id: str | None = None):
        super().__init__(session_id)
        self.websocket = websocket
        self.client_host = websocket.client.host if websocket.client else "?"
        self._pending_tasks = set()
        self._pending_tasks_lock = threading.Lock()
        self._closing = False
        self._close_task = None

    def _track_task(self, task):
        with self._pending_tasks_lock:
            self._pending_tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task):
        with self._pending_tasks_lock:
            self._pending_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[WebSocket] Async task failed: {e}")

    def send_command(self, cmd: str, *args, **kwargs):
        if cmd == "echo_on":
            return
        if cmd == "prompt_masked":
            cmd = "prompt"
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        data = json.dumps([cmd, args, kwargs])
        try:
            if threading.get_ident() == self.thread_id:
                task = self.loop.create_task(self.websocket.send_text(data))
            else:
                task = asyncio.run_coroutine_threadsafe(
                    self.websocket.send_text(data), self._resolve_loop()
                )
            self._track_task(task)
        except Exception as e:
            logger.debug(f"[WebSocket] Error sending command: {e}")

    async def _close_websocket(self):
        with self._pending_tasks_lock:
            pending = list(self._pending_tasks)
        if pending:
            try:
                pending_awaitables = [
                    asyncio.wrap_future(task, loop=asyncio.get_running_loop())
                    if isinstance(task, concurrent.futures.Future)
                    else task
                    for task in pending
                ]
                await asyncio.wait_for(
                    asyncio.gather(*pending_awaitables, return_exceptions=True),
                    timeout=0.25,
                )
            except asyncio.TimeoutError:
                for pending_task in pending:
                    pending_task.cancel()
        try:
            await self.websocket.close()
        except Exception:
            pass

    def close(self):
        if self._closing:
            return
        self._closing = True
        try:
            if threading.get_ident() == self.thread_id:
                self._close_task = self.loop.create_task(self._close_websocket())
            else:
                self._close_task = asyncio.run_coroutine_threadsafe(self._close_websocket(), self._resolve_loop())
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
            client_host = websocket.client.host if websocket.client else "?"
            if is_ip_banned(client_host):
                logger.warning(f"Host {client_host} in temp ban list has tried to connect.")
                await websocket.close()
                return

            await websocket.accept()

            conn_id = get_connection_manager().generate_connection_id()
            connection = WebSocketConnection(websocket=websocket, session_id=conn_id)
            if not get_connection_manager().register_connection(conn_id, connection):
                return

            try:
                while True:
                    raw_message = await websocket.receive_text()
                    if len(raw_message) > settings.WEBSOCKET_MAX_MESSAGE_SIZE:
                        if _should_log_oversize(client_host):
                            logger.warning(
                                f"[WebSocket] Message too large from {client_host} ({len(raw_message)} bytes > {settings.WEBSOCKET_MAX_MESSAGE_SIZE} bytes)"
                            )
                        try:
                            await websocket.close(code=1009, reason="Message too large")
                        except Exception:
                            pass
                        connection._closing = True
                        break
                    get_connection_manager().handle_command(connection, raw_message)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.warning(f"[WebSocket] Connection error: {e}")
            finally:
                get_connection_manager().disconnect(connection)
