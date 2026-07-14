from __future__ import annotations
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class MapCommand(Command):
    key = "map"
    desc = "Toggle map display."
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.map_enabled = not caller.map_enabled
        if caller.map_enabled:
            caller.msg("Map enabled.")
            caller.msg(map_enable="")
        else:
            caller.msg("Map disabled.")
            caller.msg(map_disable="")

