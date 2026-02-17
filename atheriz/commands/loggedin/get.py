from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.singletons.node import Node


class GetCommand(Command):
    key = "get"
    desc = "Get an object."

    def setup_parser(self):
        self.parser.add_argument("object", type=str, help="object to get or all")
        self.parser.add_argument("source", type=str, nargs="*", help="container to get from")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        loc: Node | None = caller.location
        if not loc:
            caller.msg("No.")
            return

        obj_name = args.object
        # Filter out 'from' from source args (handles "get foo from bar")
        source_parts = [p for p in args.source if p.lower() != "from"]
        source_name = " ".join(source_parts) if source_parts else None

        if obj_name == "all":
            # Get all from a container or from the room
            if source_name:
                container = caller.search(source_name)
                if not container:
                    container = loc.search(source_name)
                if not container:
                    caller.msg(f"'{source_name}' not found.")
                    return
                source = container[0]
            else:
                source = loc

            for obj in list(source.contents):
                if not obj.at_pre_get(caller) or obj.id == caller.id:
                    continue
                obj.move_to(caller)
                loc.msg_contents(
                    text=(f"{caller.name} picked up {obj.name}.", {"type": "get"}),
                    from_obj=caller,
                    exclude=caller,
                )
                caller.msg(f"You picked up: {obj.name}")
                obj.at_get(caller)
            return

        # Get specific object from a container or from the room
        if source_name:
            container = caller.search(source_name)
            if not container:
                container = loc.search(source_name)
            if not container:
                caller.msg(f"'{source_name}' not found.")
                return
            found = container[0].search(obj_name)
            if not found:
                caller.msg(f"'{obj_name}' not found in {container[0].name}.")
                return
        else:
            if not loc.access(caller, "get"):
                caller.msg("You can't get something from here!")
                return
            found = loc.search(obj_name)
            if not found:
                caller.msg("Object not found.")
                return

        for f in found:
            if not f.at_pre_get(caller):
                caller.msg(f"You can't get {f.name}.")
                continue
            f.move_to(caller)
            loc.msg_contents(
                text=(f"{caller.name} picked up {f.name}.", {"type": "get"}),
                from_obj=caller,
                exclude=caller,
            )
            caller.msg(f"You picked up: {f.name}")
            f.at_get(caller)
