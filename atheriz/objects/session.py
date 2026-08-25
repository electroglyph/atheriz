from __future__ import annotations
import time
import threading
from atheriz.logger import logger
from atheriz.objects.base_account import Account
from typing import TYPE_CHECKING
import asyncio
import atheriz.settings as settings

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.base_obj import Object


class Session:
    def __init__(self, account: Account | None = None, connection: Connection | None = None):
        # Guards puppet / puppet_stack / input_future, which are written by
        # game workers and read by the per-connection input drain (#31).
        # Scalar fields (term/map dims, screenreader) are single atomic
        # stores under the GIL and need no lock.
        self.lock = threading.RLock()
        self.account = account
        self.connection = connection
        self.last_puppet: Object | None = None
        self.puppet: Object | None = None
        # stack of (prev_puppet, target). Each target carries its own
        # `_puppet_restore` manifest (excluded from pickling by __getstate__).
        # Lives on the session (never pickled) so transient restore state stays off saved objects.
        self.puppet_stack: list = []
        self.term_width: int = settings.CLIENT_DEFAULT_WIDTH
        self.term_height: int = settings.CLIENT_DEFAULT_HEIGHT
        self.map_width: int = 0
        self.map_height: int = 0
        self.screenreader: bool = False
        self.conn_time = 0.0
        self.input_future: asyncio.Future | None = None
        self._input_masked: bool = False

    def at_connect(self):
        self.conn_time = time.time()

    def at_disconnect(self):
        with self.lock:
            future = self.input_future
            self.input_future = None
            masked = self._input_masked
            self._input_masked = False
            stack, self.puppet_stack = self.puppet_stack, []
            puppet = self.puppet
        if masked and self.connection is not None:
            try:
                self.connection.send_command("echo_on")
            except Exception:
                pass
        if future is not None:
            try:
                loop = future.get_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                def _do_cancel():
                    if not future.done():
                        try:
                            future.cancel()
                        except asyncio.InvalidStateError:
                            pass
                try:
                    loop.call_soon_threadsafe(_do_cancel)
                except RuntimeError:
                    logger.debug("Input future's loop already closed; skipping cancel.")
            else:
                if not future.done():
                    try:
                        future.cancel()
                    except asyncio.InvalidStateError:
                        pass
        # unwind any in-progress puppet chain before autosave so a
        # mid-puppet disconnect doesn't persist a mutated target as a real PC.
        while stack:
            _prev, target = stack.pop()
            if restore := getattr(target, "_puppet_restore", None):
                target.__dict__.update(restore)
                del target._puppet_restore
        if puppet:
            elapsed = time.time() - self.conn_time
            if self.conn_time > 0.0 and elapsed > 0:
                # Clear the session link before accruing so the seconds_played
                # getter stops adding the live delta; otherwise this session's
                # time is baked in twice.
                puppet.session = None
                puppet.seconds_played += elapsed
            puppet.at_disconnect()
        if self.account:
            self.account.at_disconnect()

    def msg(self, *args, **kwargs):
        self.connection.msg(*args, **kwargs)

    async def prompt(self, text: str, mask: bool = False) -> str:
        """
        Send a prompt to the user and await their response.
        """
        prev = None
        prev_masked = False
        need_restore = False
        with self.lock:
            prev = self.input_future
            prev_masked = self._input_masked
            try:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
            except RuntimeError:
                loop = None
                if self.connection is not None:
                    try:
                        loop = getattr(self.connection, "loop", None)
                        if loop is None and hasattr(self.connection, "_resolve_loop"):
                            try:
                                loop = self.connection._resolve_loop()
                            except Exception:
                                loop = None
                    except Exception:
                        loop = None
                if loop is None:
                    try:
                        from atheriz.globals.get import get_async_threadpool

                        loop = get_async_threadpool().loop
                    except Exception:
                        loop = None
                if loop is not None and hasattr(loop, "create_future"):
                    future = loop.create_future()
                else:
                    future = asyncio.Future()
            if prev is not None and not prev.done():
                if prev_masked and not mask:
                    need_restore = True
            else:
                prev = None
            self.input_future = future
            self._input_masked = mask
        if prev is not None:
            try:
                loop = prev.get_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                def _do_set():
                    if not prev.done():
                        try:
                            prev.set_result("")
                        except asyncio.InvalidStateError:
                            pass
                try:
                    loop.call_soon_threadsafe(_do_set)
                except RuntimeError:
                    if not prev.done():
                        try:
                            prev.set_result("")
                        except asyncio.InvalidStateError:
                            pass
            else:
                if not prev.done():
                    try:
                        prev.set_result("")
                    except asyncio.InvalidStateError:
                        pass
        if need_restore:
            try:
                self.connection.send_command("echo_on")
            except Exception:
                pass
        if mask:
            try:
                self.connection.send_command("prompt_masked", text)
            except Exception:
                pass
        else:
            self.msg(text)
        return await future
