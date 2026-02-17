from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.singletons.node import Node


class GiveCommand(Command):
    key = "give"
    desc = "Give an object to someone else."

    # pyrefly: ignore
    def setup_parser(self):
        self.parser.add_argument("object", type=str, help="object to give (from inventory) or all")
        self.parser.add_argument("target", type=str, nargs="*", help="who to give the object to")

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        if not args:
            caller.msg(self.print_help())
            return

        obj_name = args.object
        target_parts = [p for p in args.target if p.lower() != "to"]
        if not target_parts:
            caller.msg("Give it to whom?")
            return
        target_name = " ".join(target_parts)

        loc: "Node" | None = caller.location
        if not loc:
            caller.msg("No.")
            return

        targets = loc.search(target_name)
        if not targets:
            caller.msg(f"Could not find '{target_name}' here.")
            return
        target = targets[0]

        if target.id == caller.id:
            caller.msg("You already have that!")
            return

        if obj_name == "all":
            objs_to_give = list(caller.contents)
        else:
            objs_to_give = caller.search(obj_name)

        if not objs_to_give:
            caller.msg("You don't have that.")
            return

        given_any = False
        for obj in list(objs_to_give):
            if obj.id == target.id:
                continue
            if not obj.at_pre_give(caller, target):
                continue
            if obj.move_to(target):
                given_any = True
                caller.msg(f"You give {obj.name} to {target.name}.")
                target.msg(f"{caller.name} gives you {obj.name}.")
                loc.msg_contents(
                    text=(f"{caller.name} gives {obj.name} to {target.name}.", {"type": "give"}),
                    from_obj=caller,
                    exclude=(caller, target),
                )
                obj.at_give(caller, target)
            else:
                caller.msg(f"You can't give {obj.name} to {target.name}.")

        if not given_any and obj_name == "all":
            caller.msg("You have nothing to give.")
