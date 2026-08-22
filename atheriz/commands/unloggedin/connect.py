from __future__ import annotations
import time
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING
from atheriz.globals.objects import filter_by, TEMP_BANNED_IPS, TEMP_BANNED_LOCK, get
from atheriz.objects.base_account import Account
import atheriz.settings as settings
from atheriz.logger import logger

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.base_obj import Object


async def char_selection(caller: Connection, account: Account) -> None:
    """Prompt a logged-in account to choose a character to puppet.

    When `settings.CHAR_CREATION_ENABLED` is on, the selection screen always
    mentions that typing 'new' creates a fresh character, whether or not the
    account already has characters. Otherwise, an account without characters
    is told it has nothing to play.
    """
    while caller.session.puppet is None:
        chars: list[Object] = get(account.characters)
        text = "Please select a character to play: \r\n"
        for x, c in enumerate(chars):
            tag = " [banned]" if getattr(c, "is_banned", False) else ""
            text += f"{x}. {c.name}{tag}\r\n"
        if settings.CHAR_CREATION_ENABLED:
            text += "\r\nor type 'new' to create a new character\r\n"
        if not chars and not settings.CHAR_CREATION_ENABLED:
            caller.msg("This account has no characters to play.")
            return
        caller.msg(text)
        choice = await caller.session.prompt("Enter your choice:")
        if settings.CHAR_CREATION_ENABLED and choice.strip().lower() == "new":
            from atheriz.commands.unloggedin.new import NewCharacterCommand

            await NewCharacterCommand().run(caller, None)
            continue
        try:
            choice = int(choice)
        except ValueError:
            caller.msg("Invalid choice.")
            continue
        if choice >= len(chars) or choice < 0:
            caller.msg("Invalid choice.")
            continue
        if getattr(chars[choice], "is_banned", False):
            msg = "That character is banned."
            reason = getattr(chars[choice], "ban_reason", None)
            if reason:
                msg += f" Reason: {reason}"
            caller.msg(msg)
            continue
        if not account.at_pre_puppet(chars[choice]):
            caller.msg("This character is not available.")
            continue
        char = chars[choice]
        with char.lock:
            if getattr(char, "session", None) is not None or getattr(char, "is_deleted", False):
                caller.msg("This character is not available.")
                continue
            with caller.session.lock:
                caller.session.puppet = char
                char.session = caller.session
                caller.session.conn_time = time.time()
        char.at_post_puppet()


class ConnectCommand(Command):
    key = "connect"
    desc = "Connect to an existing account with a password."

    def setup_parser(self):
        self.parser.add_argument("account_name", help="The name of the account to connect to.")
        self.parser.add_argument("password", help="The password for the account.")

    # pyrefly: ignore
    async def run(self, caller: Connection, args):
        account_name = args.account_name
        password = args.password
        accounts = filter_by(lambda x: x.is_account and x.name == account_name)

        if not accounts:
            # don't say "account not found" for security reasons
            caller.msg("Invalid password.")
            return

        if len(accounts) > 1:
            logger.error(f"Multiple accounts found for {account_name}")
            caller.msg("Error: Please contact server admin.")
            return

        account: Account = accounts[0]

        if not account.check_password(password):
            caller.msg("Invalid password.")
            caller.failed_login_attempts += 1
            if caller.failed_login_attempts > settings.MAX_LOGIN_ATTEMPTS:
                host = getattr(caller, "client_host", "?")
                logger.warning(
                    f"Host {host} has been banned for {settings.LOGIN_ATTEMPT_COOLDOWN} seconds due to too many failed login attempts."
                )
                caller.msg("Too many failed login attempts. Please try again later.")
                caller.close()
                with TEMP_BANNED_LOCK:
                    TEMP_BANNED_IPS[host] = time.time() + settings.LOGIN_ATTEMPT_COOLDOWN
            return

        if account.is_banned:
            caller.msg(f"You have been banned from this server. Reason: {account.ban_reason or 'None specified'}")
            caller.close()
            return
        caller.session.account = account
        caller.send_command("logged_in")
        await char_selection(caller, account)
