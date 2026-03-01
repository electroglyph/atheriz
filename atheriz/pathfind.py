from typing import TYPE_CHECKING
from atheriz.singletons.get import get_node_handler
import heapq

if TYPE_CHECKING:
    from atheriz.objects.nodes import Node, NodeLink
    from atheriz.objects.base_obj import Object


class PathNode:
    def __init__(self, parent=None, position=None):
        self.parent = parent
        self.position = position
        self.g = 0
        self.h = 0
        self.f = 0

    def __eq__(self, other):
        return self.position == other.position

    def __lt__(self, other):
        return self.f < other.f

    def __gt__(self, other):
        return self.f > other.f


def get_path(current_node):
    path = []
    current = current_node
    while current is not None:
        path.append(current.position)
        current = current.parent
    return path[::-1]  # return reversed path


def get_adjacent_cells(origin: tuple, map: list, width: int, height: int):
    results = []
    if origin[0] > 0 and map[origin[1] * width + (origin[0] - 1)]:
        results.append((origin[0] - 1, origin[1]))
    if origin[0] < width - 1 and map[origin[1] * width + (origin[0] + 1)]:
        results.append((origin[0] + 1, origin[1]))
    if origin[1] > 0 and map[(origin[1] - 1) * width + origin[0]]:
        results.append((origin[0], origin[1] - 1))
    if origin[1] < height - 1 and map[(origin[1] + 1) * width + origin[0]]:
        results.append((origin[0], origin[1] + 1))
    return results


def astar(
    start: Node, end: Node, caller: Object | None = None
) -> tuple[bool, list[Node], list[Node]]:
    nh = get_node_handler()

    def get_link_nodes(node: Node) -> list[Node]:
        result = []
        if node.links:
            for l in node.links:
                n = nh.get_node(l.coord)
                if n:
                    result.append(n)
        return result

    def get_link_nodes_caller(node: Node) -> list[Node]:
        result = []
        if node.links:
            doors = nh.get_doors(node.coord)
            for l in node.links:
                if doors:
                    d = doors.get(l.name)
                    if d and d.closed:
                        if not d.access(caller, "open"):
                            continue
                        if d.locked and not d.access(caller, "unlock"):
                            continue
                n = nh.get_node(l.coord)
                if n:
                    result.append(n)
        return result

    start_node = PathNode(None, start)
    start_node.g = start_node.h = start_node.f = 0
    end_node = PathNode(None, end)
    end_node.g = end_node.h = end_node.f = 0
    open_list = []
    closed_list = []
    iterations = 0
    grid = start.grid
    if not grid:
        return False, [], []
    max_iterations = len(grid) * 3
    heapq.heapify(open_list)
    heapq.heappush(open_list, start_node)
    current_node = start_node
    while True:
        iterations += 1
        closed_list.append(current_node)
        if current_node.position == end_node.position:
            return True, get_path(current_node), [c.position for c in closed_list]
        if iterations > max_iterations:
            return False, get_path(current_node), [c.position for c in closed_list]
        children = []
        nodes = get_link_nodes(current_node.position) if caller is None else get_link_nodes_caller(current_node.position)
        for n in nodes:
            node = PathNode(current_node, n)
            children.append(node)
        for child in children:
            if child in closed_list:
                continue
            child.g = current_node.g + 1
            child.h = (
                ((child.position.coord[1] - end_node.position.coord[1]) ** 2)
                + ((child.position.coord[2] - end_node.position.coord[2]) ** 2)
                + ((child.position.coord[3] - end_node.position.coord[3]) ** 2)
            )
            if child.position.coord[0] != end_node.position.coord[0]:  # coord = (area, x, y, z)
                child.h **= 2
            child.f = child.g + child.h
            if child in open_list:
                idx = open_list.index(child)
                if child.g < open_list[idx].g:
                    open_list[idx] = child
            else:
                heapq.heappush(open_list, child)
        if len(open_list) == 0:
            return False, get_path(current_node), [c.position for c in closed_list]
        current_node = heapq.heappop(open_list)
