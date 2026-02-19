from atheriz.commands.base_cmd import Command
from atheriz.objects.base_obj import Object
from atheriz.singletons.get import get_node_handler
from atheriz.singletons.objects import delete_objects
import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.nodes import Node

class DeleteCommand(Command):
    key = "delete"
    desc = "Delete an object permanently."
    category = "Building"
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", nargs='+', help="Object to delete.")
        self.parser.add_argument("-r", "--recursive", action="store_true", help="Delete contents recursively.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        
        if not args.target:
            caller.msg("Delete what?")
            return
            
        target_name = " ".join(args.target).strip()
        
        target = None
        if target_name.lower() == "here":
            target = caller.location
        else:
            raw = target_name
            if raw.startswith("(") and raw.endswith(")"):
                raw = raw[1:-1]
            
            if "," in raw:
                parts = [p.strip() for p in raw.split(",")]
                if len(parts) == 4:
                    try:
                        area = parts[0]
                        x = int(parts[1])
                        y = int(parts[2])
                        z = int(parts[3])
                        coord = (area, x, y, z)
                        target = get_node_handler().get_node(coord)
                    except ValueError:
                        pass

        if not target:
            # Search in inventory first
            target = caller.search(target_name)
            
            # If not found in inventory, search in location
            if not target:
                loc: Node = caller.location
                if loc and loc.access(caller, "view"):
                    target = loc.search(target_name)
                    if not target:
                        caller.msg(f"No match found for '{target_name}'.")
                        return
                    elif len(target) > 1:
                        caller.msg(f"Multiple matches for '{target_name}'.")
                        return
                    else:
                        target = target[0]
            elif len(target) > 1:
                caller.msg(f"Multiple matches for '{target_name}'.")
                return
            else:
                target: Object = target[0]

        if not target.access(caller, "delete"):
            caller.msg("You do not have permission to delete that.")
            return

        full_name = target.get_display_name(caller)
        result = target.delete(caller, args.recursive)
        
        if result is None:
            caller.msg("Deletion aborted.")
            return

        if isinstance(result, list):
            delete_objects(result)
            count = len(result)
        else:
            node_count, ops = result
            if ops:
                delete_objects(ops)
            count = node_count + len(ops) + 1

        if count > 1:
            caller.msg(f"Deleted or moved {full_name}, {count} objects total.")
        else:
            caller.msg(f"Deleted {full_name}.")
        return
