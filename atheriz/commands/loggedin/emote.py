from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class EmoteCommand(Command):
    key = "emote"
    aliases = [":"]
    category = "Communication"
    desc = "Emote something."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("text", nargs="*", help="Text to emote.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        loc = caller.location
        if args.text and loc:
            loc.msg_contents(f"{caller.name} {" ".join(args.text)}", from_obj=caller)
        else:
            caller.msg(self.print_help())
