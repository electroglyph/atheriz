from __future__ import annotations
from atheriz.globals.objects import save_objects
from atheriz.globals.objects import add_object
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import filter_by
from atheriz.objects.base_obj import Object
import atheriz.settings as settings
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from atheriz.objects.base_account import Account

def at_server_start():
    pass


def at_server_stop():
    pass


def at_server_reload():
    pass

def at_char_create(account_name: str, char_name: str, password: str):
    """Create a new character. This is only called when a character is created from the command line.

    Args:
        account_name (str): The name of the account to create the character for.
        char_name (str): The name of the character to create.
        password (str): The password of the account.
    """
    results: list[Account] = filter_by(lambda x: x.is_account and x.name == account_name)
    nh = get_node_handler()
    home = nh.get_node(settings.DEFAULT_HOME)
    if results:
        for r in results:
            if not r.check_password(password):
                print(
                    f"Account '{account_name}' already exists with a different password..."
                )
                return
            if len(r.characters) >= settings.MAX_CHARACTERS:
                print(
                    f"Account '{account_name}' already has {settings.MAX_CHARACTERS} characters..."
                )
                return
            character = Object.create(None, char_name, is_pc=True)
            character.home = home
            r.add_character(character)
            add_object(character)
            character.move_to(home)
            save_objects()
            print("Success! Character created.")
            return

    print(f"Creating account '{account_name}'...")
    account = Account.create(account_name, password)
    if not account:
        print(f"Account '{account_name}' already exists.")
        return
    print(f"Creating character '{char_name}'...")
    character = Object.create(None, char_name, is_pc=True)
    character.home = home
    account.add_character(character)
    add_object(account)
    add_object(character)
    character.move_to(home)
    save_objects()
    print("Success! Account and character created.")