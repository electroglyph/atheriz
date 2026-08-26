from __future__ import annotations
import time
from atheriz.commands.base_cmd import Command
from atheriz.objects.base_account import Account
from atheriz.commands.unloggedin.connect import char_selection
from atheriz.globals.objects import (
    apply_creation_cooldown,
    clear_creation_cooldown,
    try_reserve_creation_cooldown,
)
from atheriz.commands.unloggedin.validation import validate_account_name, validate_password
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
        if not try_reserve_creation_cooldown("account", rate_key, time.monotonic(), settings.CREATION_COOLDOWN):
            caller.msg("Creation is temporarily rate-limited. Please try again later.")
            return

        name = await caller.session.prompt("Enter an account name:")
        name = name.strip()
        if err := validate_account_name(name):
            clear_creation_cooldown(rate_key)
            caller.msg(err)
            return

        password = await caller.session.prompt("Enter a password:")
        if err := validate_password(password):
            clear_creation_cooldown(rate_key)
            caller.msg(err)
            return

        try:
            account = Account.create(name, password)
        except ValueError as e:
            clear_creation_cooldown(rate_key)
            caller.msg(str(e))
            return
        if account is None:
            clear_creation_cooldown(rate_key)
            caller.msg(f"Account with this name ({name}) already exists.")
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
