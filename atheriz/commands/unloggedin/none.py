from __future__ import annotations
from atheriz.commands.base_cmd import Command
from atheriz.globals.get import get_unloggedin_cmdset
import atheriz.settings as settings
from polyleven import levenshtein
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection

_IGNORED_COMMANDS = list(settings.AUTO_ALIAS_IGNORED_KEYS)


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
        commands = [
            cmd for cmd in get_unloggedin_cmdset().commands.keys() if cmd not in _IGNORED_COMMANDS
        ]
        scores = [levenshtein(args.none, cmd) for cmd in commands]
        best_match = commands[scores.index(min(scores))]
        caller.msg(
            f"Command{f' \"{args.none}\"' if args.none else ''} not found, did you mean: \"{best_match}\"?"
        )
