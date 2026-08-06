from __future__ import annotations
import time
from atheriz.commands.base_cmd import Command
from atheriz.objects.base_account import Account
from atheriz.commands.unloggedin.connect import char_selection
from atheriz.globals.objects import (
    apply_creation_cooldown,
    creation_cooldown_active,
)
from typing import TYPE_CHECKING
import atheriz.settings as settings

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection


class CreateCommand(Command):
    key = "create"
    desc = "Create a new account."
    use_parser = False

    # pyrefly: ignore
    async def run(self, caller: Connection, args):
        if not settings.ACCOUNT_CREATION_ENABLED:
            caller.msg("Account creation is not enabled.")
            return

        host = getattr(caller, "client_host", None)
        rate_key = host if isinstance(host, str) and host else id(caller)
        if creation_cooldown_active("account", rate_key, time.monotonic()):
            caller.msg("Creation is temporarily rate-limited. Please try again later.")
            return

        name = await caller.session.prompt("Enter an account name:")
        name = name.strip()
        if not name:
            caller.msg("Name cannot be empty.")
            return

        password = await caller.session.prompt("Enter a password:")
        if not password:
            caller.msg("Password cannot be empty.")
            return

        if creation_cooldown_active("account", rate_key, time.monotonic()):
            caller.msg("Creation is temporarily rate-limited. Please try again later.")
            return
        try:
            account = Account.create(name, password)
        except ValueError as e:
            caller.msg(str(e))
            return
        apply_creation_cooldown(
            "account", rate_key, time.monotonic(), settings.CREATION_COOLDOWN
        )
        caller.session.account = account
        caller.send_command("logged_in")
        if settings.CHAR_CREATION_ENABLED:
            await char_selection(caller, account)
        else:
            caller.msg("Account created. Character creation is not enabled.")
