import ast
from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


class SetCommand(Command):
    key = "set"
    category = "Building"
    desc = "Set an attribute on an object."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Object to modify (name, #id, 'me', or 'here').")
        self.parser.add_argument("attribute", help="Attribute name to set.")
        self.parser.add_argument("value", help="Value to set (evaluated with ast.literal_eval).")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        target_str = args.target

        if target_str == "me":
            target = caller
        elif target_str == "here":
            target = caller.location
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

        attr = args.attribute
        raw_value = args.value

        try:
            value = ast.literal_eval(raw_value)
        except (ValueError, SyntaxError):
            # If literal_eval fails, treat it as a plain string
            value = raw_value

        if not hasattr(target, attr):
            caller.msg(f"Warning: '{attr}' is a new attribute on {target.name}.")

        setattr(target, attr, value)
        caller.msg(f"Set {target.name}.{attr} = {repr(value)}")


class UnsetCommand(Command):
    key = "unset"
    category = "Building"
    desc = "Delete an attribute from an object."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Object to modify (name, #id, 'me', or 'here').")
        self.parser.add_argument("attribute", help="Attribute name to delete.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        target_str = args.target

        if target_str == "me":
            target = caller
        elif target_str == "here":
            target = caller.location
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

        attr = args.attribute

        if not hasattr(target, attr):
            caller.msg(f"{target.name} has no attribute '{attr}'.")
            return

        delattr(target, attr)
        caller.msg(f"Deleted {target.name}.{attr}")
