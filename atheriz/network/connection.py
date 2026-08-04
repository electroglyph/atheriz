from __future__ import annotations
import asyncio
import threading
import time
import traceback
from collections import deque
from typing import TYPE_CHECKING
import json
import atheriz.settings as settings
from atheriz.logger import logger
from atheriz.utils import strip_ansi

if TYPE_CHECKING:
    from atheriz.objects.session import Session

class BaseConnection:
    """
    Abstract interface for all network connections.
    Specific protocol implementations (WebSocket, Telnet, etc) should inherit
    from this and implement `send_command` and `close`.
    """

    def __init__(self, session_id: str | None = None):
        from atheriz.objects.session import Session
        self.session_id = session_id
        self.session = Session(connection=self)
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None
        self.thread_id = threading.get_ident()
        self.lock = threading.RLock()
        self.failed_login_attempts = 0
        # Per-connection input pipeline (issue #31): handlers queued by the
        # protocol loop are run FIFO by a single drain task on the game
        # threadpool, preserving input ordering per connection.
        self._input_queue = deque()
        self._input_running = False
        self._last_input_busy = 0.0

    def enqueue_input(self, handler, args: list, kwargs: dict):
        """Queue one input handler for serialized execution on the game
        threadpool. Called from the protocol event loop; returns immediately.

        When this connection already has CONNECTION_INPUT_QUEUE_LIMIT pending
        messages, the newest message is dropped and the client gets a
        throttled busy reply (#32)."""
        from atheriz.globals.get import get_async_threadpool
        busy = False
        with self.lock:
            if len(self._input_queue) >= settings.CONNECTION_INPUT_QUEUE_LIMIT:
                now = time.monotonic()
                if now - self._last_input_busy < 1.0:
                    return
                self._last_input_busy = now
                busy = True
                start = False
            else:
                self._input_queue.append((handler, args, kwargs))
                start = not self._input_running
                if start:
                    self._input_running = True
        if busy:
            self.msg("Server busy; input dropped.")
            return
        if not start:
            return
        if not get_async_threadpool().add_task(self._drain_input):
            # queue full (#32): drop pending input for this connection
            with self.lock:
                self._input_queue.clear()
                self._input_running = False

    def _drain_input(self):
        """Worker-side: run queued input handlers FIFO until the queue empties."""
        while True:
            with self.lock:
                if not self._input_queue:
                    self._input_running = False
                    return
                handler, args, kwargs = self._input_queue.popleft()
            try:
                handler(self, args, kwargs)
            except Exception:
                name = getattr(handler, "__name__", handler)
                logger.error(f"[Network] Input handler '{name}' failed: {traceback.format_exc()}")

    def clear_pending_input(self):
        """Drop queued-but-unrun input (used on disconnect)."""
        with self.lock:
            self._input_queue.clear()

    # pyrefly: ignore
    def send_command(self, cmd: str, *args, **kwargs):
        """
        Send a command to the client.
        Must be implemented by child classes.
        """
        raise NotImplementedError

    def msg(self, *args, **kwargs):
        """
        Send a text message to this connection.
        Maps simple messages to the robust `send_command` interface.
        """
        cmd = "text"
        if not args and not kwargs:
            return
        args = list(args) or []
        if kwargs:
            text = kwargs.pop("text", None)
            if text:
                args.insert(0, text)
            else:
                k, v = kwargs.popitem()
                cmd = k
                if args:
                    args = [v] + args
                else:
                    args = [v]

        if cmd == "text" and args:
            if not args[0].endswith(("\r\n", "\n")):
                args[0] += "\r\n"
            if self.session.screenreader:
                args[0] = strip_ansi(args[0])
        self.send_command(cmd, *args, **kwargs)

    # pyrefly: ignore
    def close(self):
        """
        Close the connection.
        Must be implemented by child classes.
        """
        raise NotImplementedError
