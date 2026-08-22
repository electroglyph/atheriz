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

    def _resolve_loop(self):
        """Return the loop to schedule cross-thread work on. Falls back to the
        running loop, then the async threadpool loop, when the connection was
        constructed outside an event loop (self.loop is None)."""
        if self.loop is not None:
            return self.loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            from atheriz.globals.get import get_async_threadpool
            return get_async_threadpool().loop

    def enqueue_input(self, handler, args: list, kwargs: dict):
        """Queue one input handler for serialized execution on the game
        threadpool. Called from the protocol event loop; returns immediately.

        When this connection already has CONNECTION_INPUT_QUEUE_LIMIT pending
        messages, the newest message is dropped and the client gets a
        throttled busy reply (#32).

        Invariant: _input_running == True implies a submitted-but-not-yet-
        running or actively running drain worker. The worker-slot reservation
        and the threadpool submission share one critical section, so a rejected
        submission can never coexist with a live worker; on rejection the
        queue is kept intact and retried by the next enqueue."""
        from atheriz.globals.get import get_async_threadpool
        notify_busy = False
        with self.lock:
            if len(self._input_queue) >= settings.CONNECTION_INPUT_QUEUE_LIMIT:
                now = time.monotonic()
                if now - self._last_input_busy < 1.0:
                    return
                self._last_input_busy = now
                notify_busy = True
            else:
                self._input_queue.append((handler, args, kwargs))
                if self._input_running:
                    return
                self._input_running = True
                if get_async_threadpool().add_task(self._drain_input):
                    return
                # No worker was started and none can be running (we held the
                # reservation), so reverting the flag is safe; keep queued input.
                self._input_running = False
                now = time.monotonic()
                if now - self._last_input_busy >= 1.0:
                    self._last_input_busy = now
                    notify_busy = True
        if notify_busy:
            logger.warning(
                f"[Network] Input queue submission rejected (pool full); "
                f"{len(self._input_queue)} message(s) pending retry"
            )
            self.msg("Server busy; input dropped.")

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

    def launch_draw(self):
        """Ask a browser-capable client to open the draw editor."""
        self.send_command("launch_draw")

    def msg(self, *args, **kwargs):
        """
        Send a text message to this connection.
        Maps simple messages to the robust `send_command` interface.
        """
        cmd = "text"
        if not args and not kwargs:
            return
        args = list(args) or []
        outgoing_kwargs = dict(kwargs)
        if outgoing_kwargs:
            text = outgoing_kwargs.pop("text", None)
            if text:
                args.insert(0, text)
            elif outgoing_kwargs:
                k, v = outgoing_kwargs.popitem()
                cmd = k
                args = [v] + args

        if cmd == "text" and args:
            if not isinstance(args[0], str):
                args[0] = str(args[0])
            if not args[0].endswith(("\r\n", "\n")):
                args[0] += "\r\n"
            if self.session.screenreader:
                args[0] = strip_ansi(args[0])
        self.send_command(cmd, *args, **outgoing_kwargs)

    # pyrefly: ignore
    def close(self):
        """
        Close the connection.
        Must be implemented by child classes.
        """
        raise NotImplementedError
