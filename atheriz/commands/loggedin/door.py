from atheriz.commands.base_cmd import Command
from atheriz.singletons.get import get_node_handler
from atheriz.objects.nodes import NodeLink, Node
from atheriz.objects.base_door import Door
import atheriz.settings as settings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class DoorCommand(Command):
    key = "door"
    category = "Building"
    desc = "Manage doors."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("-n", "--north", action="store_true", help="North")
        self.parser.add_argument("-s", "--south", action="store_true", help="South")
        self.parser.add_argument("-e", "--east", action="store_true", help="East")
        self.parser.add_argument("-w", "--west", action="store_true", help="West")
        self.parser.add_argument("-u", "--up", action="store_true", help="Up")
        self.parser.add_argument("-d", "--down", action="store_true", help="Down")
        self.parser.add_argument("-r", "--remove", action="store_true", help="Remove door")
        self.parser.add_argument("-a", "--auto", action="store_true", help="Auto create destination room if it doesn't exist")
        self.parser.add_argument("args", nargs="*", help="Other args")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if args.remove and not any(
            [args.north, args.south, args.east, args.west, args.up, args.down]
        ):
            caller.msg("You must specify a direction when removing a door.")
            return
        # loc.coord = tuple["area", "x", "y", "z"]
        loc = caller.location
        if not loc:
            caller.msg("You have an invalid location.")
            return
        if args.remove:
            if args.north:
                nh = get_node_handler()
                # coord[0] = area, coord[1] = x, coord[2] = y, coord[3] = z
                to_coord = loc.coord.copy()
                door_coord = loc.coord.copy()
                door_coord[2] += 1
                # y + 2 because the door is between the two rooms
                to_coord[2] += 2
                to_node = nh.get_node(to_coord)
                if not to_node:
                    if args.auto:
                        to_node = Node(to_coord)
                        nh.add_node(to_node)
                    else:
                        caller.msg(f"There is no node at the destination coord {to_coord}, use -a to auto-create it.")
                        return
                door_node = nh.get_node(door_coord)
                if door_node:
                    nh.remove_node(door_coord)
                    caller.msg(f"Removed node at {door_coord} since a door is being placed there.")
                to_links = to_node.get_links()
                
            if args.south:
                pass
            if args.east:
                pass
            if args.west:
                pass
            if args.up:
                pass
            if args.down:
                pass
        else:
            if args.north:
                pass
            if args.south:
                pass
            if args.east:
                pass
            if args.west:
                pass
            if args.up:
                pass
            if args.down:
                pass

        caller.msg("Door command is not yet fully implemented.")
