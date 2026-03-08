from atheriz.commands.base_cmd import Command
from atheriz.globals.get import get_node_handler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class MoveCommand(Command):
    key = "move"
    desc = "Move to a coordinate."
    category = "Building"

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("coord", nargs="+", help="Coordinate: area x y z  or  (area,x,y,z)")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args or not args.coord:
            caller.msg(self.print_help())
            return

        raw = " ".join(args.coord).strip()

        # Strip surrounding parentheses if present
        if raw.startswith("(") and raw.endswith(")"):
            raw = raw[1:-1]

        # Split by comma or whitespace
        if "," in raw:
            parts = [p.strip() for p in raw.split(",")]
        else:
            parts = raw.split()

        if len(parts) != 4:
            caller.msg("Usage: move <area> <x> <y> <z>  or  move (<area>,<x>,<y>,<z>)")
            return

        area = parts[0]
        try:
            x = int(parts[1])
            y = int(parts[2])
            z = int(parts[3])
        except ValueError:
            caller.msg("x, y, and z must be integers.")
            return

        coord = (area, x, y, z)
        nh = get_node_handler()
        node = nh.get_node(coord)
        if not node:
            caller.msg(f"No node found at {coord}.")
            return

        caller.move_to(node, force=True)
        caller.msg(f"Moved to {coord}.")
