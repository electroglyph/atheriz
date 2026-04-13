import time
from atheriz.commands.base_cmd import Command
from atheriz.menu import Choice, MenuEngine
from atheriz.objects.base_obj import Object
from atheriz.globals.get import get_node_handler
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
            return

        desc = await caller.session.prompt(
            "Enter a short description of your character:"
        )
        desc = desc.strip()

        character = Object.create(None, name, desc=desc, is_pc=True)
        character.is_temporary = True
        character.gender = gender
        caller.session.puppet = character
        character.session = caller.session
        caller.session.connect_time = time.time()

        nh = get_node_handler()
        home = nh.get_node(settings.DEFAULT_HOME)
        if home:
            character.home = home
            character.move_to(home)

        character.at_post_puppet()
