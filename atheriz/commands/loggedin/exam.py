from atheriz.commands.base_cmd import Command
from atheriz.singletons.objects import get
from atheriz.objects.base_obj import Object
from atheriz.websocket import Connection
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


class ExamineCommand(Command):
    """
    Examine an object and display all its attributes.

    Usage:
      examine <target>
      examine #<id>
    """

    key = "examine"
    aliases = ["exam", "ex"]
    desc = "Examine an object to see its attributes."
    category = "Building"

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", nargs="?", help="Object to examine (name or #id).")

    def run(self, caller: Object | Connection, args):
        if not args:
            caller.msg(self.print_help())
            return
        target_str = args.target

        if not target_str:
            target = caller.location
            if not target:
                caller.msg("You are nowhere to examine.")
                return
        elif target_str == "me":
            target = caller
        elif target_str.startswith("#"):
            try:
                obj_id = int(target_str[1:])
                results = get(obj_id)
                if not results:
                    caller.msg(f"No object found with ID {obj_id}.")
                    return
                target = results[0]
            except ValueError:
                caller.msg("Invalid ID format. Use #<number>.")
                return
        else:
            if target_str:
                matches = caller.search(target_str)
                if not matches:
                    loc: Node = caller.location
                    if loc and loc.access(caller, "view"):
                        matches = loc.search(target_str)

                if not matches:
                    caller.msg(f"No match found for '{target_str}'.")
                    return
                elif len(matches) > 1:
                    caller.msg(f"Multiple matches for '{target_str}':")
                    for m in matches:
                        caller.msg(f"  #{m.id} {m.name}")
                    return
                else:
                    target = matches[0]

        caller.msg(f"Examining {target.name} ({target.id if not target.is_node else str(target)}):")

        ignore = ["access"]

        attrs = vars(target)
        sorted_keys = sorted(attrs.keys())

        for key in sorted_keys:
            if key in ignore:
                continue
            val = attrs[key]
            # Convert to string to avoid issues
            try:
                val_str = str(val)
            except Exception:
                val_str = "<unprintable>"

            type_name = type(val).__name__
            caller.msg(f"  {key}: {val_str} ({type_name})")
