from atheriz.commands.base_cmd import Command
import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node

class LookCommand(Command):
    key = "look"
    aliases = ["l"]
    desc = "Look at your current location or an object."

    def setup_parser(self):
        self.parser.add_argument("target", nargs=argparse.REMAINDER, help="Object to look at.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            loc: Node | None = caller.location
            if not loc or not loc.access(caller, "view"):
                caller.msg("You can't tell if your eyes are open or closed.")
                return
            caller.msg(caller.at_look(loc))
            return
        if args.target:
            target_name = " ".join(args.target)
            target = caller.search(target_name)
            if not target:
                loc: Node | None = caller.location
                if loc and loc.access(caller, "view"):
                    target = loc.search(target_name)
                    if not target:
                        caller.msg(f"No match found for '{target_name}'.")
                        return
                    elif len(target) > 1:
                        caller.msg(f"Multiple matches for '{target_name}'.")
                        return
                    else:
                        target = target[0]
            elif len(target) > 1:
                caller.msg(f"Multiple matches for '{target_name}'.")
                return
            else:
                target = target[0]

            caller.msg(caller.at_look(target))
        else:
            loc: Node | None = caller.location
            if not loc or not loc.access(caller, "view"):
                caller.msg("You can't tell if your eyes are open or closed.")
                return
            caller.msg(caller.at_look(loc))
