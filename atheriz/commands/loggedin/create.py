import argparse
from atheriz.commands.base_cmd import Command
from atheriz.objects.base_obj import Object
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection


class CreateCommand(Command):
    key = "create"
    category = "Building"
    desc = "Create a new object."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("name", type=str, help="name of the object to create")
        self.parser.add_argument(
            "-p", "--is_pc", action="store_true", help="create as player character"
        )
        self.parser.add_argument("-i", "--is_item", action="store_true", help="create as item")
        self.parser.add_argument("-n", "--is_npc", action="store_true", help="create as NPC")
        self.parser.add_argument(
            "-m", "--is_mapable", action="store_true", help="make object mapable"
        )
        self.parser.add_argument(
            "-c", "--is_container", action="store_true", help="make object a container"
        )
        self.parser.add_argument(
            "-t", "--is_tickable", action="store_true", help="make object tickable"
        )
        self.parser.add_argument(
            "desc", type=str, help="description of the object to create", nargs=argparse.REMAINDER
        )

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        obj = Object.create(
            session=caller.session,
            name=args.name,
            desc=" ".join(args.desc) if args.desc else "",
            is_pc=args.is_pc,
            is_item=args.is_item,
            is_npc=args.is_npc,
            is_mapable=args.is_mapable,
            is_container=args.is_container,
            is_tickable=args.is_tickable,
        )
        obj.move_to(caller)
        caller.msg(f"Created object '{obj.name}' (ID: {obj.id}).")
