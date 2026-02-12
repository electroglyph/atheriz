from atheriz.commands.base_cmd import Command
from atheriz.singletons.get import get_unloggedin_cmdset
from polyleven import levenshtein
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection


class NoneCommand(Command):
    key = "none"
    desc = "None."
    hide = True

    def setup_parser(self):
        self.parser.add_argument("none", type=str, help="None.", nargs="*")

    # pyrefly: ignore
    def run(self, caller: Connection, args):
        if not args:
            caller.msg("Command not found.")
            return
        args.none = " ".join(args.none)
        commands = [cmd for cmd in get_unloggedin_cmdset().commands.keys() if cmd != "none"]
        scores = [levenshtein(args.none, cmd) for cmd in commands]
        best_match = commands[scores.index(min(scores))]
        caller.msg(
            f"Command{f' \"{args.none}\"' if args.none else ''} not found, did you mean: \"{best_match}\"?"
        )
