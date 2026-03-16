from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.globals.node import Node


class NounCommand(Command):
    key = "noun"
    desc = "Set noun description in current room"
    category = "Building"

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("noun", type=str, help="noun to add or change")
        self.parser.add_argument("desc", type=str, nargs="*", help="desc to set for the noun")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args or not args.noun or not args.desc:
            caller.msg(self.print_help())
            return
        loc: Node | None = caller.location
        if not loc:
            caller.msg("No.")
            return
        mode = "Updated" if loc.get_noun(args.noun) else "Added"
        desc = " ".join(args.desc)
        loc.add_noun(args.noun, desc)
        caller.msg(f"{mode} '{args.noun}'.")