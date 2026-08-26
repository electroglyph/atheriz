from __future__ import annotations
from atheriz.commands.base_cmd import Command
from atheriz.globals.get import get_loggedin_cmdset
import atheriz.settings as settings
from polyleven import levenshtein
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.base_obj import Object

_IGNORED_COMMANDS = list(settings.AUTO_ALIAS_IGNORED_KEYS)


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
        internal = getattr(caller, "internal_cmdset", None)
        if internal is not None:
            commands = [cmd for cmd in internal.get_keys() if cmd not in _IGNORED_COMMANDS]
        else:
            commands = []
        commands2 = [
            cmd for cmd in get_loggedin_cmdset().get_keys() if cmd not in _IGNORED_COMMANDS
        ]
        choices = commands + commands2
        # include external verbs from location and inventory (help.py pattern)
        try:
            loc = getattr(caller, "location", None)
            if loc:
                for o in getattr(loc, "contents", []):
                    cs = getattr(o, "external_cmdset", None)
                    if cs:
                        for k in cs.get_keys():
                            if k not in _IGNORED_COMMANDS and k not in choices:
                                choices.append(k)
            for o in getattr(caller, "contents", []):
                cs = getattr(o, "external_cmdset", None)
                if cs:
                    for k in cs.get_keys():
                        if k not in _IGNORED_COMMANDS and k not in choices:
                            choices.append(k)
        except Exception:
            pass
        if choices:
            scores = [levenshtein(args.none, cmd) for cmd in choices]
            best_match = choices[scores.index(min(scores))]
            caller.msg(
                f"Command{f' \"{args.none}\"' if args.none else ''} not found, did you mean: \"{best_match}\"?"
            )
        else:
            caller.msg(f"Command{f' \"{args.none}\"' if args.none else ''} not found.")
