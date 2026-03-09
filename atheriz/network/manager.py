import threading
import json
from typing import Callable, TYPE_CHECKING
from atheriz.logger import logger
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK

if TYPE_CHECKING:
    from .connection import BaseConnection
    from atheriz.globals.asyncthreadpool import AsyncThreadPool

class ConnectionManager:
    """
    Manages all connections and orchestrates message handling across protocols.
    Replaces the older WebSocketManager to be protocol-agnostic.
    """

    def __init__(self):
        from atheriz.globals.get import get_async_threadpool
        from atheriz.inputfuncs import InputFuncs

        self._connections: dict[str, "BaseConnection"] = {}
        self._lock = threading.RLock()
        self._message_handlers: dict[str, Callable] = {}
        self._connection_counter = 0
        self.atp: "AsyncThreadPool" = get_async_threadpool()
        
        self.input_funcs = InputFuncs()
        
        # Register handlers from InputFuncs
        for name, handler in self.input_funcs.get_handlers().items():
            self.register_handler(name, handler)

    def generate_connection_id(self) -> str:
        with self._lock:
            self._connection_counter += 1
            return f"conn_{self._connection_counter}"

    def register_connection(self, conn_id: str, connection: "BaseConnection"):
        with self._lock:
            self._connections[conn_id] = connection
        logger.info(f"[Network] Connection opened: {conn_id} (total: {self.connection_count})")

    def disconnect(self, connection: "BaseConnection"):
        with self._lock:
            conn_id = None
            for cid, conn in self._connections.items():
                if conn is connection:
                    conn_id = cid
                    break
            
            if conn_id:
                del self._connections[conn_id]
                if connection.session:
                    connection.session.at_disconnect()
                logger.info(f"[Network] Connection closed: {conn_id} (total: {self.connection_count})")

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def get_all_connections(self) -> list["BaseConnection"]:
        with self._lock:
            return list(self._connections.values())

    def broadcast(self, text: str):
        connections = self.get_all_connections()
        for conn in connections:
            try:
                conn.msg(text)
            except Exception as e:
                logger.error(f"[Network] Broadcast error: {e}")

    def register_handler(self, message_type: str, handler: Callable):
        with self._lock:
            self._message_handlers[message_type] = handler

    def handle_command(self, connection: "BaseConnection", raw_message: str):
        """
        Process an incoming message from a connection.
        Expected raw_message format: usually JSON list `[cmd, args, kwargs]` 
        but protocols can map native wire constructs to this logic directly if needed.
        """
        try:
            # First try parsing as JSON (from websocket)
            # If a telnet connection sends raw string, the protocol implementation
            # should wrap it or parse it before calling handle_command.
            # We'll expect handle_command receives raw JSON if it's from WebSocket,
            # but Telnet could just inject data differently. So we'll decouple JSON loading.
            
            data = json.loads(raw_message)

            if not isinstance(data, list) or len(data) < 1:
                logger.warning(f"[Network] Invalid message format (not list or empty): {raw_message}")
                return

            cmd = data[0]
            args = data[1] if len(data) > 1 else []
            kwargs = data[2] if len(data) > 2 else {}

            self.dispatch(connection, cmd, args, kwargs)

        except json.JSONDecodeError:
            logger.warning(f"[Network] Error decoding JSON: {raw_message}")
        except Exception as e:
            logger.error(f"[Network] Error handling message: {e}", exc_info=True)

    def dispatch(self, connection: "BaseConnection", cmd: str, args: list, kwargs: dict):
        """Routes a verified, structured command to the proper handler."""
        handler = self._message_handlers.get(cmd)
        if handler:
            handler(connection, args, kwargs)
        else:
            # print(f"[Network] Unknown command: {cmd}")
            pass
