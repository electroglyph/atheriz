import time
from atheriz.objects.base_account import Account
from typing import TYPE_CHECKING
import asyncio
import atheriz.settings as settings
from datetime import datetime

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.base_obj import Object


class Session:
    def __init__(self, account: Account | None = None, connection: Connection | None = None):
        self.account = account
        self.connection = connection
        self.last_puppet: Object | None = None
        self.puppet: Object | None = None
        self.term_width: int = settings.CLIENT_DEFAULT_WIDTH
        self.term_height: int = settings.CLIENT_DEFAULT_HEIGHT
        self.map_width: int = 0
        self.map_height: int = 0
        self.screenreader: bool = False
        self.conn_time = 0
        self.cmd_last = None
        self.cmd_total = 0
        self.last_cmd = ""
        self.input_future: asyncio.Future | None = None

    def at_connect(self):
        self.conn_time = time.time()

    def at_disconnect(self):
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
