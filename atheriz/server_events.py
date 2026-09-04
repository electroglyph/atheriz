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

def _lost_pc_name_race(char_name_lower: str, my_id: int) -> bool:
    """True if another PC already claims this character name and wins ties.

    Lowest id wins, so concurrent creators converge deterministically no
    matter how the re-checks interleave: the smallest id never sees a
    smaller dupe, every larger id removes itself.
    """
    dupes = filter_by(
        lambda x: getattr(x, "is_pc", False)
        and getattr(x, "name", "").lower() == char_name_lower
        and x.id != my_id
    )
    return any(d.id < my_id for d in dupes)


def at_char_create(account_name: str, char_name: str, password: str):
    """Create a new character. This is only called when a character is created from the command line.

    Args:
        account_name (str): The name of the account to create the character for.
        char_name (str): The name of the character to create.
        password (str): The password of the account.
    """
    from atheriz.commands.unloggedin.validation import (
        validate_account_name,
        validate_character_name,
        validate_password,
    )

    err = validate_password(password)
    if err is not None:
        print(err)
        return
    err = validate_character_name(char_name)
    if err is not None:
        print(err)
        return
    exists_lc = char_name.lower()
    if filter_by(lambda x: getattr(x, "is_pc", False) and getattr(x, "name", "").lower() == exists_lc):
        print(f"Character name '{char_name}' already exists.")
        return
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
                r.characters.append(character.id)
                object.__setattr__(r, "is_modified", True)
            if _lost_pc_name_race(exists_lc, character.id):
                with r.lock:
                    try:
                        r.characters.remove(character.id)
                    except ValueError:
                        pass
                    object.__setattr__(r, "is_modified", True)
                remove_object(character)
                print(f"Character name '{char_name}' already exists.")
                return
            character.move_to(home)
            save_objects()
            object.__setattr__(r, "is_modified", True)
            print("Success! Character created.")
            return

    err = validate_account_name(account_name)
    if err is not None:
        print(err)
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
    if _lost_pc_name_race(exists_lc, character.id):
        remove_object(character)
        print(f"Character name '{char_name}' already exists.")
        return
    character.home = home
    with account.lock:
        account.characters.append(character.id)
        object.__setattr__(account, "is_modified", True)
    character.move_to(home)
    save_objects()
    object.__setattr__(account, "is_modified", True)
    print("Success! Account and character created.")