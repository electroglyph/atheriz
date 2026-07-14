from __future__ import annotations
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class DescCommand(Command):
    key = "desc"
    category = "Building"
    desc = "Change current room description, use \\n for newlines."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("text", nargs="*", help="New description.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        if args.text:
            loc = caller.location
            if not loc:
                caller.msg("You are nowhere!")
                return
            loc.desc = " ".join(args.text).replace("\\n", "\n")
            caller.msg(caller.at_look(loc))
        else:
            caller.msg(self.print_help())
