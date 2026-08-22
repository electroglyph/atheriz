from __future__ import annotations
import time
from atheriz.commands.base_cmd import Command
from atheriz.menu import Choice, MenuEngine
from atheriz.objects.base_obj import Object
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import (
    apply_creation_cooldown,
    creation_cooldown_active,
)
from typing import TYPE_CHECKING
import atheriz.settings as settings

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection


def _gender_menu(context):
    def _set_gender(value):
        def callback(ctx):
            ctx.state["gender"] = value

        return callback

    def _set_custom(ctx):
        ctx.state["custom_gender"] = True

    return (
        "Select your character's gender:",
        [
            Choice(key="M", desc="Male", callback=_set_gender("Male")),
            Choice(key="F", desc="Female", callback=_set_gender("Female")),
            Choice(key="N", desc="Non-binary", callback=_set_gender("Non-binary")),
            Choice(key="C", desc="Custom", callback=_set_custom),
        ],
    )


class GuestCommand(Command):
    key = "guest"
    desc = "Create a temporary guest character and enter the game."
    use_parser = False

    async def run(self, caller: Connection, args):
        if not settings.GUEST_ENABLED:
            caller.msg("Guest accounts are not enabled.")
            return
        host = getattr(caller, "client_host", None)
        rate_key = host if isinstance(host, str) and host else id(caller)
        now = time.monotonic()
        if creation_cooldown_active("guest", rate_key, now):
            caller.msg("Creation is temporarily rate-limited. Please try again later.")
            return
        name = await caller.session.prompt("Enter a name for your guest character:")
        name = name.strip()
        if not name:
            caller.msg("Name cannot be empty.")
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

        if creation_cooldown_active("guest", rate_key, time.monotonic()):
            caller.msg("Creation is temporarily rate-limited. Please try again later.")
            return
        character = Object.create(None, name, desc=desc, is_pc=True)
        apply_creation_cooldown("guest", rate_key, time.monotonic(), settings.CREATION_COOLDOWN)
        character.is_temporary = True
        character.gender = gender
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
