from atheriz.commands.base_cmd import Command
from atheriz.objects.base_obj import Object
from atheriz.singletons.get import get_node_handler
from atheriz.singletons.objects import remove_object
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
                target = target[0]

        if target == caller:
            caller.msg("You cannot delete yourself.")
            return

        full_name = target.get_display_name(caller)
        count = target.delete(caller, args.recursive)
        if count > 1:
            caller.msg(f"Deleted or moved {full_name}, {count} objects total.")
        else:
            caller.msg(f"Deleted {full_name}.")

    def _delete_recursive(self, obj: Object) -> int:
        """
        Recursively delete an object and its contents.
        Returns the number of objects deleted.
        """
        count = 0
        if obj.contents:
             # Iterate over a copy since we are modifying the list
            for content in list(obj.contents):
                count += self._delete_recursive(content)
        
        self._delete_object(obj)
        count += 1
        return count

    def _delete_object(self, obj: Object):
        """
        Perform the actual deletion of an object.
        """
        # Remove from location
        if obj.location:
            obj.location.remove_object(obj)
            obj.location = None
            
        if obj.is_connected and obj.session and obj.session.connection:
            obj.is_deleted = True
            obj.session.account.remove_character(obj)
            obj.session.connection.close()
            
        # Remove from global registry
        remove_object(obj)
