from atheriz.commands.base_cmd import Command
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.singletons.objects import add_object, save_objects
from atheriz.singletons.get import get_node_handler
from atheriz import settings
from pathlib import Path
from typing import TYPE_CHECKING
import time

if TYPE_CHECKING:
    from atheriz.websocket import Connection


class SpamCommand(Command):
    key = "spam"
    desc = "Create multiple test accounts and characters."
    hide = True
    category = "Admin"

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_superuser

    def setup_parser(self):
        self.parser.add_argument("count", type=int, help="Number of accounts to create")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if args is None:
            caller.msg("Usage: spam <count>")
            return

        count = args.count

        if count > 1000:
            caller.msg("Maximum count is 1000.")
            return

        caller.msg(f"Creating {count} accounts and characters...")

        nh = get_node_handler()
        home = caller.location

        created = []
        start = time.time()
        for i in range(1, count + 1):
            account_name = f"account{i}"
            password = f"password{i}"
            char_name = f"char{i}"

            account = Account.create(account_name, password)
            if not account:
                caller.msg(f"Account '{account_name}' already exists, skipping...")
                continue

            character = Object.create(None, char_name, is_pc=True, is_mapable=True)
            character.symbol = "A"
            character.home = settings.DEFAULT_HOME
            character.move_to(home)
            account.add_character(character)
            add_object(account)
            add_object(character)
            save_objects()

            created.append((account_name, password, char_name))

        # Save credentials to file
        save_path = Path(settings.SAVE_PATH)
        creds_file = save_path / "spam_accounts.txt"
        with open(creds_file, "w") as f:
            f.write("# Account Name | Password | Character Name\n")
            for account_name, password, char_name in created:
                f.write(f"{account_name}|{password}|{char_name}\n")
        end = time.time()
        caller.msg(
            f"Created {len(created)} accounts/chars in {(end - start) * 1000} milliseconds. Credentials saved to {creds_file}"
        )
