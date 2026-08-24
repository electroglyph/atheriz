"""Issue tests: `connect` loops forever when an account has no characters.

`ConnectCommand.run` enters a `while caller.session.puppet is None` selection
loop. With `account.characters == []` (an empty list, distinct from `None`)
and character creation disabled, every choice is out of range, so the loop
can never terminate and the player is stuck at the character prompt forever.
"""
from __future__ import annotations

import asyncio
import concurrent.futures

import pytest

from atheriz import settings
from atheriz.commands.unloggedin.connect import ConnectCommand
from atheriz.objects.base_account import Account
from atheriz.tests.fakes import FakeConnection, make_args


class NoCharSession:
    """Session stand-in whose prompt always yields an out-of-range choice."""

    def __init__(self):
        self.account = None
        self.puppet = None
        self.connection = None
        self.prompts = []
        self.screenreader = False

    def msg(self, *args, **kwargs):
        pass

    async def prompt(self, text: str) -> str:
        self.prompts.append(text)
        await asyncio.sleep(0)
        return "0"


class TestConnectNoCharacters:
    def test_connect_with_empty_characters_terminates(
        self, global_test_env, running_loop, fixed_salt
    ):
        """INTENT: with char creation disabled, connecting an account that has
        no characters must terminate (e.g. with a message), not spin forever
        waiting for a valid choice."""
        old = settings.CHAR_CREATION_ENABLED
        settings.CHAR_CREATION_ENABLED = False
        try:
            conn = FakeConnection(session=NoCharSession())
            account = Account.create("bob", "pw1")
            account.characters = []

            cmd = ConnectCommand()
            fut = asyncio.run_coroutine_threadsafe(
                cmd.run(conn, make_args(account_name="bob", password="pw1")),
                running_loop,
            )
            try:
                fut.result(timeout=2)
            except TimeoutError:
                fut.cancel()
                try:
                    fut.result(timeout=2)
                except (concurrent.futures.CancelledError, TimeoutError):
                    pass
                pytest.fail("connect() loops forever when the account has no characters")
        finally:
            settings.CHAR_CREATION_ENABLED = old
