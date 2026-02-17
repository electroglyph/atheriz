import time
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING
from atheriz.singletons.objects import filter_by_type, TEMP_BANNED_IPS, TEMP_BANNED_LOCK, get
from atheriz.objects.base_account import Account
import atheriz.settings as settings
from atheriz.logger import logger

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.base_obj import Object


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
        accounts = filter_by_type("account", lambda x: x.name == account_name)

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
                logger.warning(
                    f"Host {caller.websocket.client.host} has been banned for {settings.LOGIN_ATTEMPT_COOLDOWN} seconds due to too many failed login attempts."
                )
                caller.msg("Too many failed login attempts. Please try again later.")
                caller.close()
                with TEMP_BANNED_LOCK:
                    TEMP_BANNED_IPS[caller.websocket.client.host] = (
                        time.time() + settings.LOGIN_ATTEMPT_COOLDOWN
                    )
            return

        if account.is_banned:
            caller.msg(
                f"You have been banned from this server. Reason: {account.ban_reason or 'None specified'}"
            )
            caller.close()
            return
        caller.session.account = account
        caller.send_command("logged_in")
        if account.characters is None:
            caller.msg("Character creation not implemented yet.")
            return
        while caller.session.puppet is None:
            text = "Please select a character to play: \r\n"
            chars: list[Object] = get(account.characters)
            for x, c in enumerate(chars):
                text += f"{x}. {c.name}\r\n"
            caller.msg(text)
            choice = await caller.session.prompt("Enter your choice:")
            try:
                choice = int(choice)
            except ValueError:
                caller.msg("Invalid choice.")
                continue
            if choice >= len(chars) or choice < 0:
                caller.msg("Invalid choice.")
                continue
            if not account.at_pre_puppet(chars[choice]):
                caller.msg("This character is not available.")
                continue
            caller.session.puppet = chars[choice]
            caller.session.puppet.session = caller.session
            caller.session.connect_time = time.time()
            caller.session.puppet.at_post_puppet()
