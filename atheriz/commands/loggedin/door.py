from atheriz.commands.base_cmd import Command
from atheriz.singletons.get import get_node_handler, get_map_handler
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
        else:
            if args.north:
                nh = get_node_handler()
                # coord[0] = area, coord[1] = x, coord[2] = y, coord[3] = z
                to_coord = list(loc.coord)
                door_coord = list(loc.coord)
                door_coord[2] += 1
                # y + 2 because the door is between the two rooms
                to_coord[2] += 2
                door_coord = tuple(door_coord)
                to_coord = tuple(to_coord)
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
                need_dest_link = True
                for l in to_links:
                    if l.name == "south":
                        if l.coord != loc.coord:
                            to_node.remove_link(l.name)
                            caller.msg(f"Removed link '{l.name}' from node at {to_coord} for linking to the wrong coord.")
                        else:
                            need_dest_link = False
                if need_dest_link:
                    link = NodeLink("south", loc.coord, ['s'])
                    to_node.add_link(link)
                    caller.msg(f"Created link '{link.name}' from node at {to_coord} linking to {loc.coord}.")
                here_links = loc.get_links()
                need_here_link = True
                for l in here_links:
                    if l.name == "north":
                        if l.coord != to_coord:
                            loc.remove_link(l.name)
                            caller.msg(f"Removed link '{l.name}' from node at {loc.coord} for linking to the wrong coord.")
                        else:
                            need_here_link = False
                if need_here_link:
                    link = NodeLink("north", to_coord, ['n'])
                    loc.add_link(link)
                    caller.msg(f"Created link '{link.name}' from node at {loc.coord} linking to {to_coord}.")
                door = Door.create(loc.coord, "north", to_coord, "south", (door_coord[1], door_coord[2]), settings.NS_CLOSED_DOOR, settings.NS_OPEN_DOOR1)
                nh.add_door(door)
                caller.msg(f"Created door at {door_coord}.")
                mh = get_map_handler()
                mi = mh.get_mapinfo(loc.coord[0], loc.coord[3])
                if mi:
                    mi.update_grid((door_coord[1], door_coord[2]), door.closed_symbol)
                    mi.render(True)
                return
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

