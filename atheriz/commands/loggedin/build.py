from atheriz.commands.base_cmd import Command
from atheriz.objects.nodes import Node, NodeLink, NodeGrid
from atheriz.singletons.get import get_node_handler, get_map_handler
import atheriz.settings as settings
from atheriz.singletons.map import MapInfo
from typing import TYPE_CHECKING
import time

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.websocket import Connection

DIRECTIONS = {
    "n": (0, 1, 0, "north", "south"),
    "e": (1, 0, 0, "east", "west"),
    "s": (0, -1, 0, "south", "north"),
    "w": (-1, 0, 0, "west", "east"),
    "u": (0, 0, 1, "up", "down"),
    "d": (0, 0, -1, "down", "up"),
    "x": (0, 0, 0, "here", "here"),
}


class BuildCommand(Command):
    key = "build"
    category = "Building"
    desc = "Build rooms, roads, and paths."

    def setup_parser(self):
        # Mode arguments - mutually exclusive
        # We handle mutual exclusivity manually or let last one win logic,
        # but argparse has add_mutually_exclusive_group
        mode_group = self.parser.add_mutually_exclusive_group()
        mode_group.add_argument("--room", action="store_true", help="Build a room")
        mode_group.add_argument("--road", action="store_true", help="Build a road")
        mode_group.add_argument("--path", action="store_true", help="Build a path")

        # Directions
        self.parser.add_argument("-x", action="store_true", help="Build here")
        self.parser.add_argument("-n", action="store_true", help="Build north")
        self.parser.add_argument("-e", action="store_true", help="Build east")
        self.parser.add_argument("-s", action="store_true", help="Build south")
        self.parser.add_argument("-w", action="store_true", help="Build west")
        self.parser.add_argument("-u", action="store_true", help="Build up")
        self.parser.add_argument("-d", action="store_true", help="Build down")

        # Options
        self.parser.add_argument("--desc", type=str, help="Set description")

        # Outline options - mutually exclusive
        outline_group = self.parser.add_mutually_exclusive_group()
        outline_group.add_argument(
            "--single", action="store_true", help="Single line for room walls"
        )
        outline_group.add_argument(
            "--double", action="store_true", help="Double line for room walls"
        )
        outline_group.add_argument(
            "--round", action="store_true", help="Rounded line for room walls"
        )
        outline_group.add_argument("--none", action="store_true", help="No room walls")

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        nh = get_node_handler()
        mh = get_map_handler()

        loc: Node | None = caller.location

        if not loc:
            caller.msg("You must be in a valid location to build.")
            return

        # If no arguments provided (no directions, no mode, no desc, no outline), show help
        has_args = (
            args.n
            or args.e
            or args.s
            or args.w
            or args.u
            or args.d
            or args.road
            or args.path
            or args.room
            or args.single
            or args.double
            or args.none
            or args.desc is not None
        )

        if not has_args:
            caller.msg(self.parser.format_help())
            return

        targets = []
        if args.n:
            targets.append("n")
        if args.e:
            targets.append("e")
        if args.s:
            targets.append("s")
        if args.w:
            targets.append("w")
        if args.u:
            targets.append("u")
        if args.d:
            targets.append("d")
        if args.x:
            targets.append("x")

        if not targets:
            if args.desc:
                loc.desc = args.desc
                caller.msg("Updated current location's description.")
                return
            else:
                caller.msg(f"{self.parser.format_help()}\n{self.parser.format_usage()}")
                return

        # default to --room when an outline style is given or no explicit mode specified
        if not args.room and not args.road and not args.path:
            args.room = True

        for d_key in targets:
            d_data = DIRECTIONS[d_key]
            dx, dy, dz, link_name, back_link_name = d_data

            c = loc.coord
            if not c:
                caller.msg("Error: Current location not found.")
                return
            new_coord = (c[0], c[1] + dx, c[2] + dy, c[3] + dz)
            new_node = nh.get_node(new_coord)

            if not new_node:
                desc = args.desc if args.desc else "Placeholder desc, use desc command to change"
                new_node = Node(new_coord, desc=desc)

                area = nh.get_area(c[0])
                if not area:
                    caller.msg("Error: Current area not found.")
                    return

                grid = area.get_grid(new_coord[3])
                if not grid:
                    grid = NodeGrid(c[0], new_coord[3])
                    area.add_grid(grid)

                grid.add_node(new_node)
                caller.msg(f"Created new node at {new_coord}.")
            else:
                caller.msg(f"Updating node at {new_coord}.")
                if args.desc:
                    with new_node.lock:
                        new_node.desc = args.desc

            if d_key != "x":
                if not self._has_link(loc, link_name):
                    loc.add_link(NodeLink(link_name, new_coord, [d_key]))

                if not self._has_link(new_node, back_link_name):
                    alias = self._get_alias(back_link_name)
                    aliases = [alias] if alias else []
                    new_node.add_link(NodeLink(back_link_name, loc.coord, aliases))

            mi = mh.get_mapinfo(new_coord[0], new_coord[3])
            if not mi:
                mi = MapInfo()
                mh.set_mapinfo(new_coord[0], new_coord[3], mi)

            def get_room_dirs(mi: MapInfo, coord: tuple[int, int]) -> tuple[bool, bool, bool, bool]:
                n, s, e, w = False, False, False, False
                if mi.pre_grid.get((coord[0], coord[1] + 1)) == settings.ROOM_PLACEHOLDER:
                    n = True
                if mi.pre_grid.get((coord[0], coord[1] - 1)) == settings.ROOM_PLACEHOLDER:
                    s = True
                if mi.pre_grid.get((coord[0] + 1, coord[1])) == settings.ROOM_PLACEHOLDER:
                    e = True
                if mi.pre_grid.get((coord[0] - 1, coord[1])) == settings.ROOM_PLACEHOLDER:
                    w = True
                return n, s, e, w

            def ensure_links(
                node: Node,
                n: bool = False,
                s: bool = False,
                e: bool = False,
                w: bool = False,
            ):

                if n:
                    if not node.has_link_name("north"):
                        link = NodeLink(
                            "north",
                            (node.coord[0], node.coord[1], node.coord[2] + 1, node.coord[3]),
                            ["n"],
                        )
                        node.add_link(link)
                    to_coord = (node.coord[0], node.coord[1], node.coord[2] + 1, node.coord[3])
                    to_node = nh.get_node(to_coord)
                    if to_node:
                        if not to_node.has_link_name("south"):
                            link = NodeLink("south", node.coord, ["s"])
                            to_node.add_link(link)

                if s:
                    if not node.has_link_name("south"):
                        link = NodeLink(
                            "south",
                            (node.coord[0], node.coord[1], node.coord[2] - 1, node.coord[3]),
                            ["s"],
                        )
                        node.add_link(link)
                    to_coord = (node.coord[0], node.coord[1], node.coord[2] - 1, node.coord[3])
                    to_node = nh.get_node(to_coord)
                    if to_node:
                        if not to_node.has_link_name("north"):
                            link = NodeLink("north", node.coord, ["n"])
                            to_node.add_link(link)

                if e:
                    if not node.has_link_name("east"):
                        link = NodeLink(
                            "east",
                            (node.coord[0], node.coord[1] + 1, node.coord[2], node.coord[3]),
                            ["e"],
                        )
                        node.add_link(link)
                    to_coord = (node.coord[0], node.coord[1] + 1, node.coord[2], node.coord[3])
                    to_node = nh.get_node(to_coord)
                    if to_node:
                        if not to_node.has_link_name("west"):
                            link = NodeLink("west", node.coord, ["w"])
                            to_node.add_link(link)

                if w:
                    if not node.has_link_name("west"):
                        link = NodeLink(
                            "west",
                            (node.coord[0], node.coord[1] - 1, node.coord[2], node.coord[3]),
                            ["w"],
                        )
                        node.add_link(link)
                    to_coord = (node.coord[0], node.coord[1] - 1, node.coord[2], node.coord[3])
                    to_node = nh.get_node(to_coord)
                    if to_node:
                        if not to_node.has_link_name("east"):
                            link = NodeLink("east", node.coord, ["e"])
                            to_node.add_link(link)

            # place map tile(s)
            if args.room:
                char = ""
                if args.single:
                    char = settings.SINGLE_WALL_PLACEHOLDER
                elif args.double:
                    char = settings.DOUBLE_WALL_PLACEHOLDER
                elif args.round:
                    char = settings.ROUNDED_WALL_PLACEHOLDER
                elif args.none:
                    pass
                else:
                    if settings.DEFAULT_ROOM_OUTLINE == "single":
                        char = settings.SINGLE_WALL_PLACEHOLDER
                    elif settings.DEFAULT_ROOM_OUTLINE == "double":
                        char = settings.DOUBLE_WALL_PLACEHOLDER
                    elif settings.DEFAULT_ROOM_OUTLINE == "rounded":
                        char = settings.ROUNDED_WALL_PLACEHOLDER
                if char:
                    mi.update_grid((new_coord[1], new_coord[2]), settings.ROOM_PLACEHOLDER)
                    mi.place_walls((new_coord[1], new_coord[2]), char)
                    n, s, e, w = get_room_dirs(mi, (new_coord[1], new_coord[2]))
                    ensure_links(new_node, n, s, e, w)

            elif args.road:
                mi.update_grid((new_coord[1], new_coord[2]), settings.ROAD_PLACEHOLDER)
            elif args.path:
                mi.update_grid((new_coord[1], new_coord[2]), settings.PATH_PLACEHOLDER)
                mi.place_walls((new_coord[1], new_coord[2]), settings.PATH_PLACEHOLDER)
            caller.move_to(new_node)

    def _get_alias(self, name):
        if name == "north":
            return "n"
        if name == "south":
            return "s"
        if name == "east":
            return "e"
        if name == "west":
            return "w"
        if name == "up":
            return "u"
        if name == "down":
            return "d"
        return ""

    def _has_link(self, node: Node, link_name: str) -> bool:
        if not node.links:
            return False
        for l in node.links:
            if l.name == link_name:
                return True
        return False
