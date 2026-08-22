from __future__ import annotations
import time
from atheriz.commands.base_cmd import Command
from atheriz.menu import MenuEngine
from atheriz.objects.base_obj import Object
from atheriz.globals.get import get_node_handler
from atheriz.commands.unloggedin.guest import _gender_menu
from atheriz.globals.objects import (
    apply_creation_cooldown,
    try_reserve_creation_cooldown,
)
from atheriz.commands.unloggedin.validation import validate_character_name
from typing import TYPE_CHECKING
import atheriz.settings as settings

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.base_account import Account


class NewCharacterCommand(Command):
    key = "new"
    desc = "Create a new character for your account."
    use_parser = False

    # pyrefly: ignore
    async def run(self, caller: Connection, args):
        if not settings.CHAR_CREATION_ENABLED:
            caller.msg("Character creation is not enabled.")
            return
        account: Account | None = caller.session.account
        if account is None:
            caller.msg("You must be logged in first.")
            return
        if len(account.characters) >= settings.MAX_CHARACTERS:
            caller.msg(f"You already have {settings.MAX_CHARACTERS} characters.")
            return

        host = getattr(caller, "client_host", None)
        rate_key = host if isinstance(host, str) and host else id(caller)
        if not try_reserve_creation_cooldown("character", rate_key, time.monotonic(), settings.CREATION_COOLDOWN):
            caller.msg("Creation is temporarily rate-limited. Please try again later.")
            return

        name = await caller.session.prompt("Enter a name for your character:")
        name = name.strip()
        if err := validate_character_name(name):
            caller.msg(err)
            return

        engine = MenuEngine(caller, _gender_menu)
        try:
            while engine.current_node:
                display = engine.get_display()
                user_input = await caller.session.prompt(display)
                if not engine.handle_input(user_input):
                    break
            gender = engine.context.state.get("gender")
            is_custom = engine.context.state.get("custom_gender")
        finally:
            engine.close()

        if is_custom:
            gender = await caller.session.prompt("Enter your character's gender:")
            gender = gender.strip()
            if not gender:
                caller.msg("Gender cannot be empty.")
                return
        elif not gender:
            caller.msg("Gender selection is required.")
            return

        desc = await caller.session.prompt(
            "Enter a short description of your character:"
        )
        desc = desc.strip()

        character = Object.create(None, name, desc=desc, is_pc=True)
        apply_creation_cooldown(
            "character", rate_key, time.monotonic(), settings.CREATION_COOLDOWN
        )
        stats = getattr(character, "stats", None)
        if stats is not None and hasattr(stats, "gender"):
            stats.gender = gender
        else:
            character.gender = gender
        account.add_character(character)
        with character.lock:
            if getattr(character, "session", None) is not None or getattr(character, "is_deleted", False):
                caller.msg("This character is not available.")
                return
            with caller.session.lock:
                caller.session.puppet = character
                character.session = caller.session
                caller.session.conn_time = time.time()

        nh = get_node_handler()
        home = nh.get_node(settings.DEFAULT_HOME)
        if home:
            character.home = home
            character.move_to(home)

        character.at_post_puppet()
