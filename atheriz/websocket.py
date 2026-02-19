import asyncio
import json
import threading
from typing import Any, Callable
from fastapi import WebSocket, WebSocketDisconnect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.singletons.asyncthreadpool import AsyncThreadPool
    from atheriz.objects.base_account import Account
from atheriz.objects.session import Session
from atheriz.connection_screen import render
from atheriz.singletons.get import get_async_threadpool, get_unloggedin_cmdset, get_loggedin_cmdset
from atheriz.singletons.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK
from atheriz.utils import strip_ansi
from atheriz.inputfuncs import InputFuncs
from atheriz.logger import logger
import atheriz.settings as settings
import time
import json

class Connection:
    """Represents a single WebSocket connection."""

    def __init__(self, websocket: WebSocket, session_id: str | None = None):
        self.websocket = websocket
        self.session_id = session_id
        self.session = Session(connection=self)
        self.loop = asyncio.get_running_loop()
        self.thread_id = threading.get_ident()
        self.lock = threading.RLock()
        self.failed_login_attempts = 0

    def send_command(self, cmd: str, *args, **kwargs):
        """Send a command to the client in the expected format: [cmd, args, kwargs]."""
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        data = json.dumps([cmd, args, kwargs])
        try:
            if threading.get_ident() == self.thread_id:
                # We are in the main thread/loop, so just create a task directly
                self.loop.create_task(self.websocket.send_text(data))
            else:
                # We are in a different thread
                asyncio.run_coroutine_threadsafe(
                    self.websocket.send_text(data), self.loop
                )
        except Exception as e:
            print(f"Error sending command: {e}")

    def msg(self, *args, **kwargs):
        """Send a message to this connection."""
        cmd = "text"
        if not args and not kwargs:
            return
        args = list(args) or []
        if kwargs:
            text = kwargs.pop("text", None)
            if text:
                args.insert(0, text)
            else:
                k,v = kwargs.popitem()
                cmd = k
                if args:
                    args = [v] + args
                else:
                    args = [v]

        if cmd == "text" and args:
            args[0] = f"{args[0]}\r\n"
            if self.session.screenreader:
                args[0] = strip_ansi(args[0])
        self.send_command(cmd, *args, **kwargs)

    async def _close_websocket(self):
        try:
            await self.websocket.close()
        except Exception:
            pass

    def close(self):
        """Close the WebSocket connection."""
        try:
            if threading.get_ident() == self.thread_id:
                self.loop.create_task(self._close_websocket())
            else:
                asyncio.run_coroutine_threadsafe(self._close_websocket(), self.loop)
        except Exception as e:
            print(f"Error closing connection: {e}")

    # def send_text_sync(self, text: str):
    #     """Send a text message synchronously (schedules task)."""
    #     asyncio.create_task(self.send_text(text))


class WebSocketManager:
    """
    Manages all WebSocket connections and message handling.

    This class is thread-safe and can be accessed from both the
    async web server thread and the game logic thread.
    """

    def __init__(self):
        self._connections: dict[str, Connection] = {}
        self._lock = threading.RLock()
        self._message_handlers: dict[str, Callable] = {}
        self._connection_counter = 0
        self.atp: AsyncThreadPool = get_async_threadpool()
        
        self.input_funcs = InputFuncs()
        
        # Register handlers from InputFuncs
        for name, handler in self.input_funcs.get_handlers().items():
            self.register_handler(name, handler)

    def _generate_connection_id(self) -> str:
        """Generate a unique connection ID."""
        with self._lock:
            self._connection_counter += 1
            return f"conn_{self._connection_counter}"

    async def connect(self, websocket: WebSocket) -> Connection | None:
        """
        Accept a new WebSocket connection.
        
        Returns:
            The Connection object for this connection.
        """
        with TEMP_BANNED_LOCK:
            if websocket.client.host in TEMP_BANNED_IPS:
                if time.time() < TEMP_BANNED_IPS[websocket.client.host]:
                    logger.warning(f"Host {websocket.client.host} in temp ban list has tried to connect.")
                    await websocket.close()
                    return None
                else:
                    del TEMP_BANNED_IPS[websocket.client.host]
        await websocket.accept()
        
        conn_id = self._generate_connection_id()
        connection = Connection(websocket=websocket, session_id=conn_id)
        
        with self._lock:
            self._connections[conn_id] = connection
        
        print(f"[WebSocket] Connection opened: {conn_id} (total: {self.connection_count})")
        return connection
    
    def disconnect(self, connection: Connection):
        """Remove a connection from the manager."""
        with self._lock:
            # Find and remove by matching the connection object
            conn_id = None
            for cid, conn in self._connections.items():
                if conn is connection:
                    conn_id = cid
                    break
            
            if conn_id:
                del self._connections[conn_id]
                if connection.session:
                    connection.session.at_disconnect()
                print(f"[WebSocket] Connection closed: {conn_id} (total: {self.connection_count})")
    
    @property
    def connection_count(self) -> int:
        """Get the current number of connections."""
        with self._lock:
            return len(self._connections)
    
    def get_all_connections(self) -> list[Connection]:
        """Get a copy of all current connections."""
        with self._lock:
            return list(self._connections.values())

    def broadcast(self, text: str):
        """Send a text message to all connected clients."""
        connections = self.get_all_connections()
        for conn in connections:
            try:
                conn.msg(text)
            except Exception as e:
                print(f"[WebSocket] Broadcast error: {e}")

    def register_handler(self, message_type: str, handler: Callable):
        """
        Register a handler for a specific message type.

        Args:
            message_type: The type of message to handle (e.g., "text", "term_size")
            handler: An async callable that takes (connection, args, kwargs) as arguments
        """
        with self._lock:
            self._message_handlers[message_type] = handler


    def handle_message(self, connection: Connection, raw_message: str):
        """
        Process an incoming message from a connection.

        Expected format: [cmd, args, kwargs] (JSON array)
        """
        # logger.info(f"Received raw message: {raw_message}")
        try:
            # Try to parse as JSON
            data = json.loads(raw_message)

            # Validate structure: [cmd (str), args (list), kwargs (dict)]
            if not isinstance(data, list) or len(data) < 1:
                print(f"[WebSocket] Invalid message format (not list or empty): {raw_message}")
                return

            cmd = data[0]
            args = data[1] if len(data) > 1 else []
            kwargs = data[2] if len(data) > 2 else {}

            # Find and call the appropriate handler
            handler = self._message_handlers.get(cmd)
            if handler:
                handler(connection, args, kwargs)
            else:
                # Silently ignore unknown commands for now, or log debug
                # print(f"[WebSocket] Unknown command: {cmd}")
                pass

        except json.JSONDecodeError:
            print(f"[WebSocket] Error decoding JSON: {raw_message}")
        except Exception as e:
            print(f"[WebSocket] Error handling message: {e}")
            import traceback

            traceback.print_exc()


websocket_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    FastAPI WebSocket endpoint handler.

    This is the main entry point for WebSocket connections.
    """
    connection = await websocket_manager.connect(websocket)

    if not connection:
        return
    try:
        while True:
            # Receive message from client
            raw_message = await websocket.receive_text()
            websocket_manager.handle_message(connection, raw_message)

    except WebSocketDisconnect:
        websocket_manager.disconnect(connection)
