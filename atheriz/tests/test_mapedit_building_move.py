"""End-to-end regression tests for editing gentown-style buildings in the
map editor.

Gentown-style buildings are stored as post_grid-only
MapInfo objects: final rendered glyphs (box-drawing walls, ANSI-wrapped door
glyphs, counter, stairs) with an EMPTY pre_grid. Core tests must not import
game-folder code (one-way dependency), so these tests replicate that output structure
faithfully by hand.

The bug this guards against had two halves:

1. The editor writes only to pre_grid; on save, batch_update() exits via
   render(True) and pre_render() REPLACES post_grid with deepcopy(pre_grid).
   With an empty pre_grid this collapsed post_grid down to just the edited
   cells: every glyph unchanged by the move (old and new wall runs crossing at
   the same coord) was wiped from the in-game map.
2. NodeGrid.apply_moves re-keyed door from/to coords but not symbol_coord, so
   the next open/close re-stamped the door glyph at its PRE-MOVE position.
"""

from threading import RLock
from unittest.mock import MagicMock, patch

from atheriz.globals import mapedit
from atheriz.globals.map import MapInfo
from atheriz.inputfuncs import InputFuncs
from atheriz.objects.base_door import Door
from atheriz.objects.nodes import Node, NodeGrid
from atheriz.tests.fakes import FakeConnection
from atheriz.utils import Coord, wrap_truecolor

AREA = "testbuilding"
Z = 0


class FakeNodeHandler:
    def __init__(self):
        self.doors = {}
        self.transitions = {}
        self.lock3 = RLock()
        self.lock2 = RLock()

    def add_transition(self, transition):
        with self.lock2:
            self.transitions[transition.to_coord] = transition

    def remove_transition(self, destination):
        with self.lock2:
            self.transitions.pop(destination, None)


class MockMapHandler:
    def __init__(self):
        self.data = {}

    def get_mapinfo(self, area, z):
        return self.data.get((area, z))

    def set_mapinfo(self, area, z, mi):
        self.data[(area, z)] = mi


def make_building_grid() -> dict[tuple[int, int], str]:
    """A gentown-like ground floor: 11x7 ring, horizontal partition wall
    across y=3 splitting two rooms, ANSI door glyph in the partition,
    counter and stairs. Mirrors floor_mapgen's output."""
    W, H = 11, 7
    g: dict[tuple[int, int], str] = {}
    for x in range(1, W - 1):
        g[(x, 0)] = "─"
        g[(x, H - 1)] = "─"
    for y in range(1, H - 1):
        g[(0, y)] = "│"
        g[(W - 1, y)] = "│"
    g[(0, 0)] = "┌"
    g[(W - 1, 0)] = "┐"
    g[(0, H - 1)] = "└"
    g[(W - 1, H - 1)] = "┘"
    # horizontal partition across y=3 with junctions on the side walls
    g[(0, 3)] = "├"
    g[(W - 1, 3)] = "┤"
    door_glyph = wrap_truecolor("━", 35, fg_bright=65)
    for x in range(1, W - 1):
        g[(x, 3)] = door_glyph if x == 5 else "─"
    # interior features (upper room / lower room)
    g[(4, 2)] = "─"  # interior segment S2 (upper room)
    g[(5, 2)] = "─"
    g[(6, 2)] = "─"
    g[(1, 4)] = "─"  # interior segment S1 (lower room)
    g[(2, 4)] = "─"
    g[(3, 4)] = "─"
    g[(2, 5)] = wrap_truecolor("█", 50)  # counter
    g[(8, 4)] = "▟"  # stairs
    return g


def make_fixture():
    """Returns (mapinfo, nodehandler, nodegrid, door) like gentown leaves
    them: nodes per room, one door through the partition, empty pre_grid."""
    grid = make_building_grid()
    mi = MapInfo(name=AREA, post_grid=dict(grid))  # pre_grid stays empty

    upper = Node(coord=Coord(AREA, 5, 2, Z))
    lower = Node(coord=Coord(AREA, 5, 4, Z))
    grid_obj = NodeGrid(AREA, Z)
    grid_obj.nodes[(upper.coord.x, upper.coord.y)] = upper
    grid_obj.nodes[(lower.coord.x, lower.coord.y)] = lower

    class Area:
        def get_grid(self, z):
            return grid_obj if z == Z else None

    class Handler(FakeNodeHandler):
        def get_area(self, name):
            return Area()

    nh = Handler()
    door = Door(
        from_coord=Coord(AREA, 5, 2, Z),
        from_exit="north",
        to_coord=Coord(AREA, 5, 4, Z),
        to_exit="south",
        symbol_coord=(5, 3),
        closed_symbol=wrap_truecolor("━", 35, fg_bright=65),
        open_symbol=wrap_truecolor("┚", 35, fg_bright=65),
    )
    nh.doors[door.from_coord] = {"north": door}
    nh.doors[door.to_coord] = {"south": door}

    return mi, nh, grid_obj, door


def client_diff(before: dict, delta: tuple[int, int]):
    """Mirror webclient computeDiff: cell-by-cell comparison of the canvas
    before vs after a pure translation; cleared cells send ''. Cells whose
    glyph is identical before/after are NOT part of the diff — the exact
    property that used to wipe them server-side."""
    dx, dy = delta
    after = {(x + dx, y + dy): ch for (x, y), ch in before.items()}
    cells = []
    for coord in sorted(set(before) | set(after)):
        b = before.get(coord)
        a = after.get(coord)
        if b != a:
            cells.append([coord[0], coord[1], a if a is not None else ""])
    return after, cells


def _ensure_builder(conn):
    puppet = getattr(getattr(conn, "session", None), "puppet", None)
    if not puppet or not getattr(puppet, "is_builder", False):
        p = MagicMock()
        p.is_builder = True
        conn.session.puppet = p


def handshake(conn) -> str:
    _ensure_builder(conn)
    key = mapedit.grant("10.0.0.1", AREA, Z)
    InputFuncs().map_edit(conn, [key, 0, []], {})
    return conn.sent[-1][1][1]


def test_building_moved_northeast_syncs_losslessly():
    mi, nh, grid_obj, door = make_fixture()
    mh = MockMapHandler()
    mh.set_mapinfo(AREA, Z, mi)
    conn = FakeConnection()
    conn.client_host = "10.0.0.1"
    _ensure_builder(conn)

    delta = (3, -2)
    before = dict(mi.post_grid)
    expected_after, glyph_cells = client_diff(before, delta)

    key = handshake(conn)

    # whole-building drag: every room node moves by the same delta
    room_ops = [
        ["room", 5, 2, 5 + delta[0], 2 + delta[1]],
        ["room", 5, 4, 5 + delta[0], 4 + delta[1]],
    ]

    with patch("atheriz.inputfuncs.get_map_handler", return_value=mh), patch(
        "atheriz.inputfuncs.get_node_handler", return_value=nh
    ), patch("atheriz.objects.nodes.get_node_handler", return_value=nh), patch(
        "atheriz.objects.base_door.get_map_handler", return_value=mh
    ):
        InputFuncs().map_edit(conn, [key, 1, glyph_cells + room_ops], {})

        # --- the in-game map must show EVERY tile at its new position ---
        assert mi.post_grid == expected_after, (
            f"missing: {sorted(set(expected_after) - set(mi.post_grid))}, "
            f"stale: {sorted(k for k in mi.post_grid if k not in expected_after)}"
        )
        assert mi.pre_grid == expected_after

        # --- rooms re-keyed ---
        assert grid_obj.get_node((5 + delta[0], 2 + delta[1])) is not None
        assert grid_obj.get_node((5 + delta[0], 4 + delta[1])) is not None
        assert grid_obj.get_node((5, 2)) is None

        # --- door fully follows its rooms ---
        assert door.from_coord == Coord(AREA, 8, 0, Z)
        assert door.to_coord == Coord(AREA, 8, 2, Z)
        assert door.symbol_coord == (8, 1)

        # --- a later open/close stamps the NEW position only ---
        old_symbol_coord = (5, 3)
        counter_glyph = before[(2, 5)]
        assert mi.post_grid[old_symbol_coord] == counter_glyph  # counter moved here
        door.map_close()
        assert mi.post_grid[(8, 1)] == door.closed_symbol
        assert mi.pre_grid[(8, 1)] == door.closed_symbol
        assert mi.post_grid[old_symbol_coord] == counter_glyph  # untouched


def test_batch_update_seeds_pre_grid_from_post_grid():
    mi = MapInfo(name=AREA, post_grid={(0, 0): "X", (1, 0): "─"})
    assert mi.pre_grid == {}
    with mi.batch_update():
        pass
    assert mi.pre_grid == {(0, 0): "X", (1, 0): "─"}
