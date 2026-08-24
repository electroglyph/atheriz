from atheriz.globals.objects import save_objects, remove_object
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import filter_by
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
import atheriz.settings as settings

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
    results: list[Account] = filter_by(lambda x: x.is_account and x.name.lower() == account_name.lower())
    nh = get_node_handler()
    home = nh.get_node(settings.DEFAULT_HOME)
    if home is None:
        print(f"Default home {settings.DEFAULT_HOME} not found; aborting char create")
        return
    if results:
        for r in results:
            if not r.check_password(password):
                print(
                    f"Account '{account_name}' already exists with a different password..."
                )
                return
            with r.lock:
                if len(r.characters) >= settings.MAX_CHARACTERS:
                    print(
                        f"Account '{account_name}' already has {settings.MAX_CHARACTERS} characters..."
                    )
                    return
            character = Object.create(None, char_name, is_pc=True)
            character.home = home
            with r.lock:
                if len(r.characters) >= settings.MAX_CHARACTERS:
                    remove_object(character)
                    print(
                        f"Account '{account_name}' already has {settings.MAX_CHARACTERS} characters..."
                    )
                    return
                r.characters.append(character.id)
            character.move_to(home)
            save_objects()
            print("Success! Character created.")
            return

    print(f"Creating account '{account_name}'...")
    try:
        account = Account.create(account_name, password)
    except ValueError:
        print(f"Account '{account_name}' already exists.")
        return
    if not account:
        print(f"Account '{account_name}' already exists.")
        return
    print(f"Creating character '{char_name}'...")
    character = Object.create(None, char_name, is_pc=True)
    character.home = home
    with account.lock:
        account.characters.append(character.id)
    character.move_to(home)
    save_objects()
    print("Success! Account and character created.")