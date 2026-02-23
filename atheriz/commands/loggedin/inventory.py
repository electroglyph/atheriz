from atheriz.commands.base_cmd import Command
from atheriz.objects.contents import group_by_name
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class InventoryCommand(Command):
    key = "inventory"
    aliases = ["i"]
    desc = "View your inventory."
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Object, args):
        contents = caller.contents
        if not contents:
            caller.msg("You are carrying nothing.")
            return
        names = group_by_name(contents, caller)
        caller.msg(f"You are carrying: {names}")
