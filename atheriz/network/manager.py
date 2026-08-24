import threading
import json
import time
from typing import Callable, TYPE_CHECKING
from atheriz.logger import logger
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK, is_ip_banned
import atheriz.settings as settings
from atheriz.utils import strip_terminal_escapes

_malformed_lock = threading.Lock()
_malformed_last: dict[str, float] = {}
_MALFORMED_WINDOW = 5.0

def _summarize_raw(raw_message: str, limit: int = 80) -> str:
    return repr(raw_message[:limit])

def _should_log_malformed(host: str) -> bool:
    now = time.monotonic()
    with _malformed_lock:
        last = _malformed_last.get(host, 0)
        if now - last < _MALFORMED_WINDOW:
            return False
        _malformed_last[host] = now
        return True

if TYPE_CHECKING:
    from .connection import BaseConnection
    from atheriz.globals.asyncthreadpool import AsyncThreadPool


def _strip_input_value(value):
    if isinstance(value, str):
        return strip_terminal_escapes(value)
    if isinstance(value, list):
        return [_strip_input_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_input_value(item) for key, item in value.items()}
    return value


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

    def register_connection(self, conn_id: str, connection: "BaseConnection") -> bool:
        """Register a connection, refusing it when the per-IP limit is reached.

        Returns True when the connection was registered, False when it was
        refused (and closed) due to ``settings.MAX_CONNECTIONS_PER_IP``.
        """
        host = getattr(connection, "client_host", "?")
        limit = settings.MAX_CONNECTIONS_PER_IP
        with self._lock:
            if is_ip_banned(host):
                logger.warning(f"[Network] Refusing connection from banned host {host}")
                try:
                    connection.close()
                except Exception:
                    pass
                return False
            if limit > 0 and host != "?":
                same_host = sum(
                    1
                    for c in self._connections.values()
                    if getattr(c, "client_host", "?") == host
                )
                if same_host >= limit:
                    logger.warning(
                        f"[Network] Refusing connection from {host}: "
                        f"per-IP limit ({limit}) reached"
                    )
                    try:
                        connection.close()
                    except Exception:
                        pass
                    return False
            self._connections[conn_id] = connection
        logger.info(f"[Network] Connection opened: {conn_id} (total: {self.connection_count})")
        return True

    def disconnect(self, connection: "BaseConnection"):
        conn_id = None
        with self._lock:
            for cid, conn in self._connections.items():
                if conn is connection:
                    conn_id = cid
                    break
            if conn_id:
                del self._connections[conn_id]
        if not conn_id:
            return
        with connection.lock:
            connection._disconnected = True
        connection.clear_pending_input()
        session = connection.session
        if session is not None:
            if not self.atp.add_task(self._do_session_disconnect, session):
                try:
                    session.at_disconnect()
                except Exception as e:
                    logger.error(f"[Network] Session teardown failed during disconnect: {e}", exc_info=True)
        try:
            connection.close()
        except Exception as e:
            logger.debug(f"[Network] Connection cleanup failed: {e}")
        logger.info(f"[Network] Connection closed: {conn_id} (total: {self.connection_count})")

    def _do_session_disconnect(self, session):
        """Run session teardown on the game threadpool so puppet unwinding,
        channel announcements, and the on-disconnect autosave never execute on
        the network event loop."""
        try:
            session.at_disconnect()
        except Exception as e:
            logger.error(f"[Network] Session teardown failed: {e}", exc_info=True)

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
            data = json.loads(raw_message)

            if not isinstance(data, list) or len(data) < 1:
                host = getattr(connection, "client_host", "?")
                if _should_log_malformed(host):
                    logger.warning(
                        f"[Network] Invalid message format from {host} ({len(raw_message)} bytes): {_summarize_raw(raw_message)}"
                    )
                return

            cmd = data[0]
            args = data[1] if len(data) > 1 else []
            kwargs = data[2] if len(data) > 2 else {}

            self.dispatch(connection, cmd, args, kwargs)

        except json.JSONDecodeError as exc:
            host = getattr(connection, "client_host", "?")
            if _should_log_malformed(host):
                logger.warning(
                    f"[Network] Error decoding JSON from {host} ({len(raw_message)} bytes): {exc.msg} at position {exc.pos}: {_summarize_raw(raw_message)}"
                )
        except Exception as e:
            logger.error(f"[Network] Error handling message: {e}", exc_info=True)

    def dispatch(self, connection: "BaseConnection", cmd: str, args: list, kwargs: dict):
        """Routes a verified, structured command to the proper handler.

        Handlers run on the game threadpool via the connection's serialized
        input queue; the protocol loop only parses, validates, and enqueues."""
        if settings.STRIP_INPUT_ESCAPE_SEQUENCES:
            args = [_strip_input_value(value) for value in args]
            kwargs = _strip_input_value(kwargs)
        handler = self._message_handlers.get(cmd)
        if handler:
            connection.enqueue_input(handler, args, kwargs)
        else:
            logger.debug(f"Unknown command: {cmd}")
