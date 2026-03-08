from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.globals.node import Node


class PutCommand(Command):
    key = "put"
    desc = "Put an object somewhere."

    def setup_parser(self):
        self.parser.add_argument("object", type=str, help="object to put")
        self.parser.add_argument(
            "destination", type=str, nargs="*", help="destination to put the object in"
        )

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        obj_name = args.object
        dest_parts = [p for p in args.destination if p.lower() not in ["in", "into"]]
        if not dest_parts:
            caller.msg(self.print_help())
            return
        dest_name = " ".join(dest_parts)

        loc: Node | None = caller.location

        dest = caller.search(dest_name)
        if not dest and loc and loc.access(caller, "put"):
            dest = loc.search(dest_name)
        if not dest:
            caller.msg(f"'{dest_name}' not found.")
            return

        if not dest[0].is_container or not dest[0].access(caller, "put"):
            caller.msg(f"You can't put anything in {dest[0].name}!")
            return

        if obj_name == "all":
            for obj in list(caller.contents):
                if obj.id == dest[0].id:
                    continue  # don't put container in itself
                obj.move_to(dest[0])
                if loc:
                    loc.msg_contents(
                        text=(f"{caller.name} put {obj.name} in {dest[0].name}.", {"type": "put"}),
                        from_obj=caller,
                        exclude=caller,
                    )
                caller.msg(f"You put {obj.name} in {dest[0].name}.")
            return

        found_obj = caller.search(obj_name)
        if not found_obj:
            caller.msg("Object not found.")
            return

        for obj in found_obj:
            obj.move_to(dest[0])
            if loc:
                loc.msg_contents(
                    text=(f"{caller.name} put {obj.name} in {dest[0].name}.", {"type": "put"}),
                    from_obj=caller,
                    exclude=caller,
                )
            caller.msg(f"You put {obj.name} in {dest[0].name}.")
