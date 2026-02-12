from random import choice
from atheriz.objects.nodes import Node, NodeLink, NodeGrid, NodeArea
from atheriz.singletons.get import get_node_handler, get_map_handler
from atheriz.singletons.map import MapInfo, LegendEntry
from atheriz.commands.base_cmd import Command
from atheriz.singletons.objects import get_by_type
import atheriz.settings as settings
from atheriz.utils import wrap_xterm256
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.base_obj import Object


class MazeCommand(Command):
    key = "maze"
    desc = "Generate a maze."
    category = "Builder"
    hide = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def __init__(self):
        super().__init__()

    # pyrefly: ignore
    def run(self, caller: Object, args):
        nh = get_node_handler()
        width = 80
        height = 30
        # map returned is a rectangular outline around grid, so actual map size returned is +2
        start = time.time()
        map1, grid1 = gen_map_and_grid(width, height, "maze1")
        map2, grid2 = gen_map_and_grid(width, height, "maze2")
        map3, grid3 = gen_map_and_grid(width, height, "maze3")
        rooms = len(grid1) + len(grid2) + len(grid3)
        elapsed = (time.time() - start) * 1000
        caller.msg(
            f"created 3 {width} x {height} mazes, {rooms} rooms, and lots of exits in: {elapsed:.2f} milliseconds"
        )
        area1 = NodeArea("maze1")
        area2 = NodeArea("maze2")
        area3 = NodeArea("maze3")
        area1.add_grid(grid1)
        area2.add_grid(grid2)
        area3.add_grid(grid3)
        nh.add_area(area1)
        nh.add_area(area2)
        nh.add_area(area3)
        mh = get_map_handler()
        maze1_exit = grid1.get_random_node()
        maze2_exit = grid2.get_random_node()
        maze3_exit = grid3.get_random_node()
        # wrap_xterm256("!",fg=9)
        mi1 = MapInfo(
            "maze1",
            None,
            map1,
            [
                LegendEntry(
                    wrap_xterm256("!", fg=9), "to maze2", (maze1_exit.coord[1], maze1_exit.coord[2])
                )
            ],
        )
        mi2 = MapInfo(
            "maze2",
            None,
            map2,
            [
                LegendEntry(
                    wrap_xterm256("!", fg=9), "to maze3", (maze2_exit.coord[1], maze2_exit.coord[2])
                )
            ],
        )
        mi3 = MapInfo(
            "maze3",
            None,
            map3,
            [
                LegendEntry(
                    wrap_xterm256("!", fg=9), "to maze1", (maze3_exit.coord[1], maze3_exit.coord[2])
                )
            ],
        )
        # mi.add_listener(caller)
        mh.set_mapinfo("maze1", 0, mi1)
        mh.set_mapinfo("maze2", 0, mi2)
        mh.set_mapinfo("maze3", 0, mi3)
        maze1_exit.add_link(NodeLink("down", ("maze2", 0, 0, 0), ["d"]))
        maze2_exit.add_link(NodeLink("down", ("maze3", 0, 0, 0), ["d"]))
        maze3_exit.add_link(NodeLink("down", ("maze1", 0, 0, 0), ["d"]))
        node = nh.get_node(("maze1", 0, 0, 0))
        end = maze1_exit
        if node:
            caller.msg(f"moving to: {node} ...")
            caller.move_to(node)
            caller.map_enabled = True


def create_maze(width: int, height: int) -> dict:
    visited = {}

    def get_valid_neighbors(coord: tuple, width: int, height: int) -> list:
        coords_to_check = []
        if coord[0] > 0:
            coords_to_check.append((coord[0] - 1, coord[1]))
        if coord[0] < width - 1:
            coords_to_check.append((coord[0] + 1, coord[1]))
        if coord[1] > 0:
            coords_to_check.append((coord[0], coord[1] - 1))
        if coord[1] < height - 1:
            coords_to_check.append((coord[0], coord[1] + 1))
        results = []
        for c in coords_to_check:
            v = visited.get(c, False)
            if not v:
                results.append(c)
        return results

    start = (0, 0)
    valid = get_valid_neighbors(start, width, height)
    current = start
    path = []
    maze = {}
    nodes = maze.get(current, [])
    done = False
    while not done:
        c = choice(valid)
        visited[c] = True
        path.append(c)
        if len(nodes) == 0:
            maze[current] = [c]
        else:
            nodes.append(c)
            maze[current] = nodes
        current = c
        nodes = maze.get(current, [])
        valid = get_valid_neighbors(current, width, height)
        while not bool(valid):
            path = path[:-1]
            if not bool(path):
                done = True
                break
            current = path[-1]
            nodes = maze.get(current, [])
            valid = get_valid_neighbors(current, width, height)
    return maze


def create_map(maze: dict, width: int, height: int, area: str):
    def get_dirs(src: tuple, dest: list, maze: dict) -> tuple:
        n = False
        s = False
        e = False
        w = False
        for d in dest:
            if d == (src[0] + 1, src[1]):
                e = True
            if d == (src[0] - 1, src[1]):
                w = True
            if d == (src[0], src[1] + 1):
                n = True
            if d == (src[0], src[1] - 1):
                s = True
        if src[0] > 0:
            nodes = maze.get((src[0] - 1, src[1]), [])
            for node in nodes:
                if node == src:
                    w = True
                    break
        if src[0] < width - 1:
            nodes = maze.get((src[0] + 1, src[1]), [])
            for node in nodes:
                if node == src:
                    e = True
                    break
        if src[1] > 0:
            nodes = maze.get((src[0], src[1] - 1), [])
            for node in nodes:
                if node == src:
                    s = True
                    break
        if src[1] < height - 1:
            nodes = maze.get((src[0], src[1] + 1), [])
            for node in nodes:
                if node == src:
                    n = True
                    break
        return (n, s, e, w)

    # map = [" "] * width * height
    map: dict[tuple[int, int], str] = {}
    grid = NodeGrid(area, 0)
    for k, v in maze.items():
        dirs = get_dirs(k, v, maze)
        node = Node((area, k[0], k[1], 0), "Somewhere in a mysterious maze.")
        if dirs[0]:
            node.add_link(NodeLink("north", (area, k[0], k[1] + 1, 0), ["n"]))
        if dirs[1]:
            node.add_link(NodeLink("south", (area, k[0], k[1] - 1, 0), ["s"]))
        if dirs[2]:
            node.add_link(NodeLink("east", (area, k[0] + 1, k[1], 0), ["e"]))
        if dirs[3]:
            node.add_link(NodeLink("west", (area, k[0] - 1, k[1], 0), ["w"]))
        grid.add_node(node)
        # map[(k[0], k[1])] = settings.DOUBLE_WALL_PLACEHOLDER
        if dirs[0] and dirs[1] and dirs[2] and dirs[3]:
            map[(k[0], k[1])] = "╬"
        elif dirs[0] and dirs[1] and dirs[2]:
            map[(k[0], k[1])] = "╠"
        elif dirs[0] and dirs[1] and dirs[3]:
            map[(k[0], k[1])] = "╣"
        elif dirs[1] and dirs[2] and dirs[3]:
            map[(k[0], k[1])] = "╦"
        elif dirs[0] and dirs[2] and dirs[3]:
            map[(k[0], k[1])] = "╩"
        elif dirs[1] and dirs[2]:
            map[(k[0], k[1])] = "╔"
        elif dirs[1] and dirs[3]:
            map[(k[0], k[1])] = "╗"
        elif dirs[0] and dirs[2]:
            map[(k[0], k[1])] = "╚"
        elif dirs[0] and dirs[3]:
            map[(k[0], k[1])] = "╝"
        elif dirs[0] or dirs[1]:
            map[(k[0], k[1])] = "║"
        elif dirs[2] or dirs[3]:
            map[(k[0], k[1])] = "═"
    return map, grid


def map_to_string(map: list, w: int, h: int):
    s = ""
    for iy in range(h - 1, -1, -1):
        for ix in range(w):
            s += "".join(map[iy * w + ix])
        s += "\n"
    return s


def gen_map_and_grid(w: int, h: int, area: str):
    maze = create_maze(w, h)
    map, grid = create_map(maze, w, h, area)
    return map, grid
