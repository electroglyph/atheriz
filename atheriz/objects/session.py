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
            masked = self._input_masked
            self._input_masked = False
            stack, self.puppet_stack = self.puppet_stack, []
            puppet = self.puppet
        if masked and self.connection is not None:
            try:
                self.connection.send_command("echo_on")
            except Exception:
                pass
        if future and not future.done():
            try:
                future.get_loop().call_soon_threadsafe(future.cancel)
            except RuntimeError:
                logger.debug("Input future's loop already closed; skipping cancel.")
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
        prev_masked = False
        prev = None
        need_restore = False
        with self.lock:
            prev = self.input_future
            prev_masked = self._input_masked
            future = asyncio.Future()
            if prev and not prev.done():
                prev.set_result("")
                if prev_masked and not mask:
                    need_restore = True
            self.input_future = future
            self._input_masked = mask
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
