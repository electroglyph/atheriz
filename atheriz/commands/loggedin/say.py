from __future__ import annotations
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class SayCommand(Command):
    key = "say"
    aliases = ["'"]
    category = "Communication"
    desc = "Say something."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("text", nargs="*", help="Text to say.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        if args.text:
            caller.at_say(" ".join(args.text), msg_self=True)
        else:
            caller.msg(self.print_help())
