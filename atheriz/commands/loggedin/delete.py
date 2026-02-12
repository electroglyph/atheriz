from atheriz.commands.base_cmd import Command
from atheriz.objects.base_obj import Object
from atheriz.singletons.objects import remove_object
import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.nodes import Node

class DeleteCommand(Command):
    key = "delete"
    desc = "Delete an object permanently."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("target", nargs='+', help="Object to delete.")
        self.parser.add_argument("-r", "--recursive", action="store_true", help="Delete contents recursively.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not caller.is_builder:
            caller.msg("You do not have permission to delete objects.")
            return

        if not args.target:
            caller.msg("Delete what?")
            return
            
        target_name = " ".join(args.target)
        
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

        # Prevent deleting self or vital objects if necessary (optional safeguard)
        if target == caller:
            caller.msg("You cannot delete yourself.")
            return

        full_name = target.get_display_name(caller)
        if args.recursive:
            count = self._delete_recursive(target)
            caller.msg(f"Deleted {full_name} and {count-1} contained objects.")
        else:
            # Move contents to current location
            if target.contents:
                location = target.location
                if location:
                    for obj in list(target.contents):
                        obj.move_to(location)
                    caller.msg(f"Moved contents of {full_name} to {location.get_display_name(caller)}.")
            
            # Delete the object
            self._delete_object(target)
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
