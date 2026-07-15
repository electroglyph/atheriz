from __future__ import annotations
import time
from atheriz.objects.base_account import Account
from typing import TYPE_CHECKING
import asyncio
import atheriz.settings as settings

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.base_obj import Object


class Session:
    def __init__(self, account: Account | None = None, connection: Connection | None = None):
        self.account = account
        self.connection = connection
        self.last_puppet: Object | None = None
        self.puppet: Object | None = None
        # ponytail: stack of (prev_puppet, target, target_orig_is_pc, target_orig_privilege).
        # Lives on the session (never pickled) so transient restore state stays off saved objects.
        self.puppet_stack: list = []
        self.term_width: int = settings.CLIENT_DEFAULT_WIDTH
        self.term_height: int = settings.CLIENT_DEFAULT_HEIGHT
        self.map_width: int = 0
        self.map_height: int = 0
        self.screenreader: bool = False
        self.conn_time = 0.0
        self.cmd_last = None
        self.cmd_total = 0
        self.last_cmd = ""
        self.input_future: asyncio.Future | None = None

    def at_connect(self):
        self.conn_time = time.time()

    def at_disconnect(self):
        if self.input_future and not self.input_future.done():
            self.input_future.cancel()
        # ponytail: unwind any in-progress puppet chain before autosave so a
        # mid-puppet disconnect doesn't persist a mutated target as a real PC.
        while self.puppet_stack:
            _prev, target, orig_is_pc, orig_priv = self.puppet_stack.pop()
            target.is_pc = orig_is_pc
            target.privilege_level = orig_priv
        if self.puppet:
            self.puppet.at_disconnect()
            self.puppet.seconds_played += time.time() - self.conn_time
        if self.account:
            self.account.at_disconnect()

    def msg(self, *args, **kwargs):
        self.connection.msg(*args, **kwargs)

    async def prompt(self, text: str) -> str:
        """
        Send a prompt to the user and await their response.
        """
        self.msg(text)
        self.input_future = asyncio.Future()
        return await self.input_future
