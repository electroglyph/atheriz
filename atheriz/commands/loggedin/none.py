from atheriz.commands.base_cmd import Command
from atheriz.singletons.get import get_loggedin_cmdset
from polyleven import levenshtein
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.base_obj import Object

_IGNORED_COMMANDS = ["none", "quit", "save"]


class NoneCommand(Command):
    key = "none"
    desc = "None."
    hide = True

    def setup_parser(self):
        self.parser.add_argument("none", type=str, help="None.", nargs="*")

    def run(self, caller: Connection | Object, args):
        if not args:
            caller.msg("Command not found.")
            return
        args.none = " ".join(args.none)
        commands = [
            cmd for cmd in caller.internal_cmdset.commands.keys() if cmd not in _IGNORED_COMMANDS
        ]
        commands2 = [
            cmd for cmd in get_loggedin_cmdset().commands.keys() if cmd not in _IGNORED_COMMANDS
        ]
        choices = commands + commands2
        if choices:
            scores = [levenshtein(args.none, cmd) for cmd in choices]
            best_match = choices[scores.index(min(scores))]
            caller.msg(
                f"Command{f' \"{args.none}\"' if args.none else ''} not found, did you mean: \"{best_match}\"?"
            )
        else:
            caller.msg(f"Command{f' \"{args.none}\"' if args.none else ''} not found.")
