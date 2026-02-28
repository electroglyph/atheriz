import pytest
from unittest.mock import patch, MagicMock
from atheriz.commands.loggedin.build import BuildCommand, DIRECTIONS
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.singletons.node import NodeHandler
from atheriz.singletons.map import MapInfo
from atheriz import settings


# ==================== Helpers ====================


class MockMapHandler:
    def __init__(self):
        self.data = {}

    def get_mapinfo(self, area, z):
        return self.data.get((area, z))

    def set_mapinfo(self, area, z, mi):
        self.data[(area, z)] = mi


class MockCaller:
    """Lightweight mock for a caller object with location and message capture."""

    def __init__(self, location=None):
        self.location = location
        self.is_builder = True
        self.messages = []
        self._moved_to = []

    def msg(self, text=None, **kwargs):
        self.messages.append(text)

    def move_to(self, destination, **kwargs):
        self.location = destination
        self._moved_to.append(destination)


def make_args(**kwargs):
    """Create a namespace-like object for parsed args."""
    defaults = {
        "n": False,
        "e": False,
        "s": False,
        "w": False,
        "u": False,
        "d": False,
        "x": False,
        "room": False,
        "road": False,
        "path": False,
        "desc": None,
        "single": False,
        "double": False,
        "round": False,
        "none": False,
    }
    defaults.update(kwargs)

    class Args:
        pass

    a = Args()
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


@pytest.fixture
def env():
    """Set up a fresh NodeHandler, MapHandler, area, grid, start node, and caller."""
    nh = NodeHandler()
    mh = MockMapHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(area="TestArea", z=0)
    start_node = Node(coord=("TestArea", 0, 0, 0))
    grid.nodes[(0, 0)] = start_node
    area.add_grid(grid)
    nh.add_area(area)

    caller = MockCaller(location=start_node)

    with patch(
        "atheriz.commands.loggedin.build.get_node_handler", return_value=nh
    ), patch(
        "atheriz.commands.loggedin.build.get_map_handler", return_value=mh
    ), patch(
        "atheriz.singletons.node.get_map_handler", return_value=mh
    ):
        yield nh, mh, area, grid, start_node, caller


# ==================== Command Attributes ====================


def test_build_command_attributes():
    cmd = BuildCommand()
    assert cmd.key == "build"
    assert cmd.category == "Building"


def test_build_command_parser_setup():
    cmd = BuildCommand()
    parser = cmd.parser
    assert parser is not None
    parsed = parser.parse_args(["-n", "--room", "--single"])
    assert parsed.n is True
    assert parsed.room is True
    assert parsed.single is True


# ==================== Error Handling ====================


def test_no_location(env):
    """Caller with no location should get an error."""
    nh, mh, area, grid, start_node, caller = env
    caller.location = None
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True))
    assert any("valid location" in m for m in caller.messages)


def test_no_args_shows_help(env):
    """No meaningful arguments should show help text."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args())
    assert len(caller.messages) > 0


def test_access_denied_for_non_builder(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    caller.is_builder = False
    assert cmd.access(caller) is False


def test_access_granted_for_builder(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    assert cmd.access(caller) is True


# ==================== Building Rooms in Directions ====================


def test_build_room_north(env):
    """build -n --room should create a node at y+1 and link both ways."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert new_node is not None

    # Start node should have a "north" link
    north_links = [l for l in start_node.get_links() if l.name == "north"]
    assert len(north_links) == 1
    assert north_links[0].coord == ("TestArea", 0, 1, 0)

    # New node should have a "south" link back
    south_links = [l for l in new_node.get_links() if l.name == "south"]
    assert len(south_links) == 1
    assert south_links[0].coord == ("TestArea", 0, 0, 0)

    # Caller should have moved
    assert caller.location == new_node


def test_build_room_south(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(s=True, room=True))

    new_node = nh.get_node(("TestArea", 0, -1, 0))
    assert new_node is not None
    south_links = [l for l in start_node.get_links() if l.name == "south"]
    assert len(south_links) == 1
    north_links = [l for l in new_node.get_links() if l.name == "north"]
    assert len(north_links) == 1


def test_build_room_east(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(e=True, room=True))

    new_node = nh.get_node(("TestArea", 1, 0, 0))
    assert new_node is not None
    east_links = [l for l in start_node.get_links() if l.name == "east"]
    assert len(east_links) == 1
    west_links = [l for l in new_node.get_links() if l.name == "west"]
    assert len(west_links) == 1


def test_build_room_west(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(w=True, room=True))

    new_node = nh.get_node(("TestArea", -1, 0, 0))
    assert new_node is not None
    west_links = [l for l in start_node.get_links() if l.name == "west"]
    assert len(west_links) == 1
    east_links = [l for l in new_node.get_links() if l.name == "east"]
    assert len(east_links) == 1


def test_build_room_up(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(u=True, room=True))

    new_node = nh.get_node(("TestArea", 0, 0, 1))
    assert new_node is not None
    up_links = [l for l in start_node.get_links() if l.name == "up"]
    assert len(up_links) == 1
    down_links = [l for l in new_node.get_links() if l.name == "down"]
    assert len(down_links) == 1


def test_build_room_down(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(d=True, room=True))

    new_node = nh.get_node(("TestArea", 0, 0, -1))
    assert new_node is not None
    down_links = [l for l in start_node.get_links() if l.name == "down"]
    assert len(down_links) == 1
    up_links = [l for l in new_node.get_links() if l.name == "up"]
    assert len(up_links) == 1


def test_build_room_here(env):
    """build -x should update the node at the current location without creating links."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(x=True, room=True, desc="Updated room"))

    # The start node should still be there, with updated desc
    assert start_node.desc == "Updated room"
    # No new links should have been created (direction was "here")
    assert len(start_node.get_links()) == 0


# ==================== Description ====================


def test_build_with_desc(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True, desc="A magical forest"))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert new_node is not None
    assert new_node.desc == "A magical forest"


def test_set_desc_only(env):
    """build --desc without direction should update current location's description."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(desc="New description"))

    assert start_node.desc == "New description"
    assert any("Updated" in m for m in caller.messages)


def test_build_existing_node_updates_desc(env):
    """Building toward an existing node with --desc should update that node's description."""
    nh, mh, area, grid, start_node, caller = env
    # Create a node to the north first
    north_node = Node(coord=("TestArea", 0, 1, 0), desc="Old desc")
    grid.nodes[(0, 1)] = north_node

    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True, desc="New desc"))

    assert north_node.desc == "New desc"
    assert any("Updating" in m for m in caller.messages)


# ==================== Mode Types ====================


def test_build_road(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, road=True))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert new_node is not None
    # MapInfo should have been created and have the road placeholder
    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    assert mi.pre_grid.get((0, 1)) == settings.ROAD_PLACEHOLDER


def test_build_path(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, path=True))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert new_node is not None
    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    assert mi.pre_grid.get((0, 1)) == settings.PATH_PLACEHOLDER


def test_default_mode_is_room(env):
    """When no mode is specified but a direction is given, mode defaults to room."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert new_node is not None
    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    # Room mode places ROOM_PLACEHOLDER
    assert mi.pre_grid.get((0, 1)) == settings.ROOM_PLACEHOLDER


# ==================== Wall Styles ====================


def test_build_with_single_walls(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True, single=True))

    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    assert mi.pre_grid.get((0, 1)) == settings.ROOM_PLACEHOLDER


def test_build_with_double_walls(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True, double=True))

    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    assert mi.pre_grid.get((0, 1)) == settings.ROOM_PLACEHOLDER


def test_build_with_round_walls(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True, **{"round": True}))

    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    assert mi.pre_grid.get((0, 1)) == settings.ROOM_PLACEHOLDER


def test_build_with_no_walls(env):
    """build --none should create a room without wall characters."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True, none=True))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert new_node is not None
    # With --none, no ROOM_PLACEHOLDER or walls should be placed (char is "")
    mi = mh.get_mapinfo("TestArea", 0)
    assert mi is not None
    # The room placeholder should NOT be in the grid since char was empty
    assert mi.pre_grid.get((0, 1)) is None


# ==================== Link Deduplication ====================


def test_link_not_duplicated_on_rebuild(env):
    """Building in the same direction twice should not duplicate links."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()

    # Build north, creating new node
    cmd.run(caller, make_args(n=True, room=True))
    north_node = nh.get_node(("TestArea", 0, 1, 0))

    # Move back
    caller.location = start_node

    # Build north again (node already exists)
    cmd.run(caller, make_args(n=True, room=True))

    north_links = [l for l in start_node.get_links() if l.name == "north"]
    assert len(north_links) == 1


# ==================== Caller Movement ====================


def test_caller_moved_after_build(env):
    """After building, the caller should be moved to the new node."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    cmd.run(caller, make_args(n=True, room=True))

    new_node = nh.get_node(("TestArea", 0, 1, 0))
    assert caller.location == new_node
    assert len(caller._moved_to) == 1


# ==================== DIRECTIONS Constant ====================


def test_directions_constant():
    """Verify the DIRECTIONS mapping is correct."""
    assert "n" in DIRECTIONS
    assert "s" in DIRECTIONS
    assert "e" in DIRECTIONS
    assert "w" in DIRECTIONS
    assert "u" in DIRECTIONS
    assert "d" in DIRECTIONS
    assert "x" in DIRECTIONS

    # north = (0, 1, 0, "north", "south")
    assert DIRECTIONS["n"] == (0, 1, 0, "north", "south")
    assert DIRECTIONS["s"] == (0, -1, 0, "south", "north")
    assert DIRECTIONS["e"] == (1, 0, 0, "east", "west")
    assert DIRECTIONS["w"] == (-1, 0, 0, "west", "east")
    assert DIRECTIONS["u"] == (0, 0, 1, "up", "down")
    assert DIRECTIONS["d"] == (0, 0, -1, "down", "up")
    assert DIRECTIONS["x"] == (0, 0, 0, "here", "here")


# ==================== Helper Methods ====================


def test_has_link(env):
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()
    assert cmd._has_link(start_node, "north") is False
    start_node.add_link(NodeLink("north", ("TestArea", 0, 1, 0), ["n"]))
    assert cmd._has_link(start_node, "north") is True
    assert cmd._has_link(start_node, "south") is False


def test_get_alias():
    cmd = BuildCommand()
    assert cmd._get_alias("north") == "n"
    assert cmd._get_alias("south") == "s"
    assert cmd._get_alias("east") == "e"
    assert cmd._get_alias("west") == "w"
    assert cmd._get_alias("up") == "u"
    assert cmd._get_alias("down") == "d"
    assert cmd._get_alias("unknown") == ""


# ==================== Multi-Direction Build ====================


def test_build_multiple_directions(env):
    """Building with multiple flags should create nodes in each direction."""
    nh, mh, area, grid, start_node, caller = env
    cmd = BuildCommand()

    # Reset caller location each time (since move_to moves them)
    caller.location = start_node
    cmd.run(caller, make_args(n=True, e=True, room=True))

    # Both nodes should exist, built from the starting room (TestArea, 0, 0, 0)
    north_node = nh.get_node(("TestArea", 0, 1, 0))
    assert north_node is not None

    # build.py keeps 'loc' as the original caller.location during the loop, 
    # so east is built from the start node, not from the north node.
    east_node = nh.get_node(("TestArea", 1, 0, 0))
    assert east_node is not None


# ==================== 2x2 Room Grid Test ====================


def test_2x2_room_grid(env):
    """
    Build a 2x2 grid of rooms:

        1(0,1) -- 2(1,1)
          |         |
        3(0,0) -- 4(1,0)

    Room 1 at (0,1): exits south to 3, east to 2
    Room 2 at (1,1): exits west to 1, south to 4
    Room 3 at (0,0): exits north to 1, east to 4
    Room 4 at (1,0): exits north to 2, west to 3
    """
    nh, mh, area, grid, start_node, caller = env

    # start_node is room 3 at (0,0,0)
    room3 = start_node
    cmd = BuildCommand()

    # From room 3, build north -> room 1
    caller.location = room3
    cmd.run(caller, make_args(n=True, room=True))
    room1 = nh.get_node(("TestArea", 0, 1, 0))
    assert room1 is not None

    # From room 1, build east -> room 2
    assert caller.location == room1
    cmd.run(caller, make_args(e=True, room=True))
    room2 = nh.get_node(("TestArea", 1, 1, 0))
    assert room2 is not None

    # From room 2, build south -> room 4
    assert caller.location == room2
    cmd.run(caller, make_args(s=True, room=True))
    room4 = nh.get_node(("TestArea", 1, 0, 0))
    assert room4 is not None

    # From room 4, build west -> room 3 (already exists, should just link)
    assert caller.location == room4
    cmd.run(caller, make_args(w=True, room=True))
    # Caller should have moved to the existing room 3
    assert caller.location == room3

    # ---- Verify all links ----

    # Room 1 (0,1): south -> room 3 (0,0), east -> room 2 (1,1)
    r1_links = {l.name: l.coord for l in room1.get_links()}
    assert "south" in r1_links
    assert r1_links["south"] == ("TestArea", 0, 0, 0)
    assert "east" in r1_links
    assert r1_links["east"] == ("TestArea", 1, 1, 0)

    # Room 2 (1,1): west -> room 1 (0,1), south -> room 4 (1,0)
    r2_links = {l.name: l.coord for l in room2.get_links()}
    assert "west" in r2_links
    assert r2_links["west"] == ("TestArea", 0, 1, 0)
    assert "south" in r2_links
    assert r2_links["south"] == ("TestArea", 1, 0, 0)

    # Room 3 (0,0): north -> room 1 (0,1), east -> room 4 (1,0)
    r3_links = {l.name: l.coord for l in room3.get_links()}
    assert "north" in r3_links
    assert r3_links["north"] == ("TestArea", 0, 1, 0)
    assert "east" in r3_links
    assert r3_links["east"] == ("TestArea", 1, 0, 0)

    # Room 4 (1,0): north -> room 2 (1,1), west -> room 3 (0,0)
    r4_links = {l.name: l.coord for l in room4.get_links()}
    assert "north" in r4_links
    assert r4_links["north"] == ("TestArea", 1, 1, 0)
    assert "west" in r4_links
    assert r4_links["west"] == ("TestArea", 0, 0, 0)

    # Verify no duplicate links on any room
    for room, name in [(room1, "Room 1"), (room2, "Room 2"), (room3, "Room 3"), (room4, "Room 4")]:
        link_names = [l.name for l in room.get_links()]
        assert len(link_names) == len(set(link_names)), f"{name} has duplicate links: {link_names}"


def test_2x2_room_grid_ensure_links(env):
    """
    Same 2x2 grid but built via ensure_links (rooms placed adjacently with
    ROOM_PLACEHOLDER so that the neighbor detection picks up adjacent rooms).

    This tests the ensure_links code path: when a room is built and its
    neighbor already has ROOM_PLACEHOLDER in the map grid, links should
    be created automatically.

        1(0,1) -- 2(1,1)
          |         |
        3(0,0) -- 4(1,0)
    """
    nh, mh, area, grid, start_node, caller = env

    room3 = start_node
    cmd = BuildCommand()

    # Build all 4 rooms with --single so walls + ROOM_PLACEHOLDER are placed
    # Room 3 is already at (0,0). Build it "here" to place map tiles.
    caller.location = room3
    cmd.run(caller, make_args(x=True, room=True, single=True))

    # Build room 1 north of room 3
    caller.location = room3
    cmd.run(caller, make_args(n=True, room=True, single=True))
    room1 = nh.get_node(("TestArea", 0, 1, 0))
    assert room1 is not None

    # Build room 2 east of room 1
    assert caller.location == room1
    cmd.run(caller, make_args(e=True, room=True, single=True))
    room2 = nh.get_node(("TestArea", 1, 1, 0))
    assert room2 is not None

    # Build room 4 south of room 2
    assert caller.location == room2
    cmd.run(caller, make_args(s=True, room=True, single=True))
    room4 = nh.get_node(("TestArea", 1, 0, 0))
    assert room4 is not None

    # At this point ensure_links should have detected adjacency:
    # Room 4 at (1,0) is adjacent to room 3 at (0,0) via west
    # and room 3 should have gotten an east link to room 4

    # Room 3 (0,0): should have north and east
    r3_links = {l.name: l.coord for l in room3.get_links()}
    assert "north" in r3_links, f"Room 3 missing north link. Links: {r3_links}"
    assert r3_links["north"] == ("TestArea", 0, 1, 0)
    assert "east" in r3_links, f"Room 3 missing east link. Links: {r3_links}"
    assert r3_links["east"] == ("TestArea", 1, 0, 0)

    # Room 4 (1,0): should have north and west
    r4_links = {l.name: l.coord for l in room4.get_links()}
    assert "north" in r4_links, f"Room 4 missing north link. Links: {r4_links}"
    assert r4_links["north"] == ("TestArea", 1, 1, 0)
    assert "west" in r4_links, f"Room 4 missing west link. Links: {r4_links}"
    assert r4_links["west"] == ("TestArea", 0, 0, 0)

    # Room 1 (0,1): should have south and east
    r1_links = {l.name: l.coord for l in room1.get_links()}
    assert "south" in r1_links
    assert "east" in r1_links

    # Room 2 (1,1): should have west and south
    r2_links = {l.name: l.coord for l in room2.get_links()}
    assert "west" in r2_links
    assert "south" in r2_links
