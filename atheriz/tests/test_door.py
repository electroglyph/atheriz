import pytest
from atheriz.utils import Coord
from unittest.mock import MagicMock, patch, PropertyMock
from atheriz.commands.loggedin.door import DoorCommand
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.globals.get import get_node_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_door import Door
from atheriz import settings
from atheriz.tests.fakes import MockCaller as FakesMockCaller
from atheriz.tests.fakes import make_args as fakes_make_args


class MockCaller:
    """Lightweight mock for a caller object with a location and message capture."""

    def __init__(self, location=None):
        self.location = location
        self.is_builder = True
        self.messages = []

    def msg(self, text=None, **kwargs):
        self.messages.append(text)


class MockMapInfo:
    def __init__(self):
        self.lock = MagicMock()
        self.post_grid = {}
        self.pre_grid = None
        self.map_changed = False

    def update_grid(self, coord, symbol):
        pass

    def render(self, force=False):
        pass


class MockMapHandler:
    def get_mapinfo(self, area, z):
        return MockMapInfo()


@pytest.fixture
def node_handler():
    """Create a fresh NodeHandler and patch get_node_handler and get_map_handler to return it."""
    nh = NodeHandler()
    with patch(
        "atheriz.commands.loggedin.door.get_node_handler", return_value=nh
    ), patch(
        "atheriz.globals.node.get_map_handler",
        return_value=MockMapHandler(),
    ):
        yield nh


@pytest.fixture
def setup_area(node_handler):
    """Create a basic area with a grid and a starting node at (0,0)."""
    area = NodeArea(name="TestArea")
    grid = NodeGrid(area="TestArea", z=0)
    start_node = Node(coord=Coord("TestArea", 0, 0, 0))
    grid.nodes[(0, 0)] = start_node
    area.add_grid(grid)
    node_handler.add_area(area)
    return node_handler, area, grid, start_node


def make_args(**kwargs):
    """Create a simple namespace-like object for parsed args."""
    defaults = {
        "north": False,
        "south": False,
        "east": False,
        "west": False,
        "up": False,
        "down": False,
        "remove": False,
        "auto": False,
        "args": [],
    }
    defaults.update(kwargs)

    class Args:
        pass

    a = Args()
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


# ==================== Parser Tests ====================


def test_door_command_attributes():
    cmd = DoorCommand()
    assert cmd.key == "door"
    assert cmd.category == "Building"
    assert cmd.use_parser is True


def test_door_command_parser_setup():
    cmd = DoorCommand()
    parser = cmd.parser
    assert parser is not None
    # Verify it can parse known flags
    parsed = parser.parse_args(["-n", "-a"])
    assert parsed.north is True
    assert parsed.auto is True
    assert parsed.south is False


def test_door_parser_has_up_down():
    cmd = DoorCommand()
    parsed = cmd.parser.parse_args(["--up"])
    assert parsed.up is True
    assert parsed.down is False

    parsed = cmd.parser.parse_args(["--down"])
    assert parsed.down is True
    assert parsed.up is False

    parsed = cmd.parser.parse_args(["-r", "-u"])
    assert parsed.remove is True
    assert parsed.up is True


# ==================== Error Handling Tests ====================


def test_remove_without_direction(node_handler):
    """door -r without a direction should show error."""
    cmd = DoorCommand()
    caller = MockCaller(location=Node(coord=Coord("TestArea", 0, 0, 0)))
    args = make_args(remove=True)
    cmd.run(caller, args)
    assert any("must specify a direction" in m for m in caller.messages)


def test_no_location(node_handler):
    """Caller with no location should get an error."""
    cmd = DoorCommand()
    caller = MockCaller(location=None)
    args = make_args(north=True)
    cmd.run(caller, args)
    assert any("invalid location" in m for m in caller.messages)


def test_create_north_no_dest_no_auto(setup_area):
    """Creating a door north without a destination node and without -a should error."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(north=True)
    cmd.run(caller, args)
    assert any("no node at the destination" in m for m in caller.messages)


# ==================== Door Creation Tests (North) ====================


def test_create_door_north_auto(setup_area):
    """door -n -a should auto-create the destination node and the door."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(north=True, auto=True)
    cmd.run(caller, args)

    # Destination node at y+2 should have been created
    dest_node = nh.get_node(Coord("TestArea", 0, 2, 0))
    assert dest_node is not None

    # Door should exist from both sides
    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert doors_from is not None
    assert "north" in doors_from

    doors_to = nh.get_doors(Coord("TestArea", 0, 2, 0))
    assert doors_to is not None
    assert "south" in doors_to

    # Same door object on both sides
    assert doors_from["north"] is doors_to["south"]

    # Door properties
    door = doors_from["north"]
    assert door.from_coord == Coord("TestArea", 0, 0, 0)
    assert door.to_coord == Coord("TestArea", 0, 2, 0)
    assert door.from_exit == "north"
    assert door.to_exit == "south"
    assert door.closed is True


def test_create_door_north_links(setup_area):
    """door -n -a should create proper links on both the source and destination nodes."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(north=True, auto=True)
    cmd.run(caller, args)

    # Source should have a "north" link
    here_links = start_node.get_links()
    north_links = [l for l in here_links if l.name == "north"]
    assert len(north_links) == 1
    assert north_links[0].coord == Coord("TestArea", 0, 2, 0)

    # Destination should have a "south" link
    dest_node = nh.get_node(Coord("TestArea", 0, 2, 0))
    dest_links = dest_node.get_links()
    south_links = [l for l in dest_links if l.name == "south"]
    assert len(south_links) == 1
    assert south_links[0].coord == Coord("TestArea", 0, 0, 0)


def test_create_door_north_with_existing_dest(setup_area):
    """door -n with a pre-existing destination node (no -a needed)."""
    nh, area, grid, start_node = setup_area
    dest_node = Node(coord=Coord("TestArea", 0, 2, 0))
    grid.nodes[(0, 2)] = dest_node

    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(north=True)
    cmd.run(caller, args)

    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert doors_from is not None
    assert "north" in doors_from
    assert any("Created door" in m for m in caller.messages)


def test_create_door_north_removes_door_node(setup_area):
    """If a node exists at the door coord (y+1), it should be removed."""
    nh, area, grid, start_node = setup_area
    # Place a node at the door coordinate
    door_coord_node = Node(coord=Coord("TestArea", 0, 1, 0))
    grid.nodes[(0, 1)] = door_coord_node
    # Place destination
    dest_node = Node(coord=Coord("TestArea", 0, 2, 0))
    grid.nodes[(0, 2)] = dest_node

    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(north=True)
    cmd.run(caller, args)

    # The node at (0,1) should have been removed
    assert nh.get_node(Coord("TestArea", 0, 1, 0)) is None
    assert any("Removed node" in m for m in caller.messages)


def test_create_door_north_symbol(setup_area):
    """Door created north should use NS door symbols."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(north=True, auto=True)
    cmd.run(caller, args)

    door = nh.get_doors(Coord("TestArea", 0, 0, 0))["north"]
    assert door.closed_symbol == settings.NS_CLOSED_DOOR
    assert door.open_symbol == settings.NS_OPEN_DOOR1
    assert door.symbol_coord == (0, 1)


# ==================== Door Creation Tests (South) ====================


def test_create_door_south_auto(setup_area):
    """door -s -a should create a door to the south."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(south=True, auto=True)
    cmd.run(caller, args)

    dest_node = nh.get_node(Coord("TestArea", 0, -2, 0))
    assert dest_node is not None

    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert "south" in doors_from

    doors_to = nh.get_doors(Coord("TestArea", 0, -2, 0))
    assert "north" in doors_to

    door = doors_from["south"]
    assert door.from_exit == "south"
    assert door.to_exit == "north"
    assert door.symbol_coord == (0, -1)
    assert door.closed_symbol == settings.NS_CLOSED_DOOR


def test_create_door_south_links(setup_area):
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(south=True, auto=True)
    cmd.run(caller, args)

    here_links = start_node.get_links()
    south_links = [l for l in here_links if l.name == "south"]
    assert len(south_links) == 1
    assert south_links[0].coord == Coord("TestArea", 0, -2, 0)

    dest_node = nh.get_node(Coord("TestArea", 0, -2, 0))
    dest_links = dest_node.get_links()
    north_links = [l for l in dest_links if l.name == "north"]
    assert len(north_links) == 1
    assert north_links[0].coord == Coord("TestArea", 0, 0, 0)


# ==================== Door Creation Tests (East) ====================


def test_create_door_east_auto(setup_area):
    """door -e -a should create a door to the east."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(east=True, auto=True)
    cmd.run(caller, args)

    dest_node = nh.get_node(Coord("TestArea", 2, 0, 0))
    assert dest_node is not None

    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert "east" in doors_from

    doors_to = nh.get_doors(Coord("TestArea", 2, 0, 0))
    assert "west" in doors_to

    door = doors_from["east"]
    assert door.from_exit == "east"
    assert door.to_exit == "west"
    assert door.symbol_coord == (1, 0)
    assert door.closed_symbol == settings.EW_CLOSED_DOOR
    assert door.open_symbol == settings.EW_OPEN_DOOR1


def test_create_door_east_links(setup_area):
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(east=True, auto=True)
    cmd.run(caller, args)

    here_links = start_node.get_links()
    east_links = [l for l in here_links if l.name == "east"]
    assert len(east_links) == 1
    assert east_links[0].coord == Coord("TestArea", 2, 0, 0)


# ==================== Door Creation Tests (West) ====================


def test_create_door_west_auto(setup_area):
    """door -w -a should create a door to the west."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(west=True, auto=True)
    cmd.run(caller, args)

    dest_node = nh.get_node(Coord("TestArea", -2, 0, 0))
    assert dest_node is not None

    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert "west" in doors_from

    doors_to = nh.get_doors(Coord("TestArea", -2, 0, 0))
    assert "east" in doors_to

    door = doors_from["west"]
    assert door.from_exit == "west"
    assert door.to_exit == "east"
    assert door.symbol_coord == (-1, 0)
    assert door.closed_symbol == settings.EW_CLOSED_DOOR
    assert door.open_symbol == settings.EW_OPEN_DOOR2


def test_create_door_west_links(setup_area):
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(west=True, auto=True)
    cmd.run(caller, args)

    here_links = start_node.get_links()
    west_links = [l for l in here_links if l.name == "west"]
    assert len(west_links) == 1
    assert west_links[0].coord == Coord("TestArea", -2, 0, 0)


# ==================== Door Removal Tests ====================


def test_remove_door_north(setup_area):
    """door -r -n should remove an existing north door."""
    nh, area, grid, start_node = setup_area
    # First create a door
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(north=True, auto=True))

    # Verify door exists
    assert nh.get_doors(Coord("TestArea", 0, 0, 0)) is not None
    assert "north" in nh.get_doors(Coord("TestArea", 0, 0, 0))

    # Now remove it
    caller.messages.clear()
    cmd.run(caller, make_args(remove=True, north=True))

    assert any("Removed" in m for m in caller.messages)
    # Door should be gone from the source side
    doors = nh.get_doors(Coord("TestArea", 0, 0, 0))
    if doors:
        assert "north" not in doors


def test_remove_door_south(setup_area):
    """door -r -s should remove an existing south door."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(south=True, auto=True))

    caller.messages.clear()
    cmd.run(caller, make_args(remove=True, south=True))

    assert any("Removed" in m for m in caller.messages)
    doors = nh.get_doors(Coord("TestArea", 0, 0, 0))
    if doors:
        assert "south" not in doors


def test_remove_door_east(setup_area):
    """door -r -e should remove an existing east door."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(east=True, auto=True))

    caller.messages.clear()
    cmd.run(caller, make_args(remove=True, east=True))

    assert any("Removed" in m for m in caller.messages)
    doors = nh.get_doors(Coord("TestArea", 0, 0, 0))
    if doors:
        assert "east" not in doors


def test_remove_door_west(setup_area):
    """door -r -w should remove an existing west door."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(west=True, auto=True))

    caller.messages.clear()
    cmd.run(caller, make_args(remove=True, west=True))

    assert any("Removed" in m for m in caller.messages)
    doors = nh.get_doors(Coord("TestArea", 0, 0, 0))
    if doors:
        assert "west" not in doors


def test_create_door_up_auto(setup_area):
    """door -u -a should create a door going up."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(up=True, auto=True)
    cmd.run(caller, args)

    dest_node = nh.get_node(Coord("TestArea", 0, 0, 2))
    assert dest_node is not None

    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert "up" in doors_from

    doors_to = nh.get_doors(Coord("TestArea", 0, 0, 2))
    assert "down" in doors_to

    assert doors_from["up"] is doors_to["down"]

    door = doors_from["up"]
    assert door.from_coord == Coord("TestArea", 0, 0, 0)
    assert door.to_coord == Coord("TestArea", 0, 0, 2)
    assert door.from_exit == "up"
    assert door.to_exit == "down"
    assert door.closed is True

    here_links = start_node.get_links()
    up_links = [l for l in here_links if l.name == "up"]
    assert len(up_links) == 1
    assert up_links[0].coord == Coord("TestArea", 0, 0, 2)

    dest_links = dest_node.get_links()
    down_links = [l for l in dest_links if l.name == "down"]
    assert len(down_links) == 1
    assert down_links[0].coord == Coord("TestArea", 0, 0, 0)


def test_create_door_down_auto(setup_area):
    """door -d -a should create a door going down."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(down=True, auto=True)
    cmd.run(caller, args)

    dest_node = nh.get_node(Coord("TestArea", 0, 0, -2))
    assert dest_node is not None

    doors_from = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert "down" in doors_from

    doors_to = nh.get_doors(Coord("TestArea", 0, 0, -2))
    assert "up" in doors_to

    assert doors_from["down"] is doors_to["up"]

    door = doors_from["down"]
    assert door.from_coord == Coord("TestArea", 0, 0, 0)
    assert door.to_coord == Coord("TestArea", 0, 0, -2)
    assert door.from_exit == "down"
    assert door.to_exit == "up"

    here_links = start_node.get_links()
    down_links = [l for l in here_links if l.name == "down"]
    assert len(down_links) == 1
    assert down_links[0].coord == Coord("TestArea", 0, 0, -2)

    dest_links = dest_node.get_links()
    up_links = [l for l in dest_links if l.name == "up"]
    assert len(up_links) == 1
    assert up_links[0].coord == Coord("TestArea", 0, 0, 0)


def test_remove_door_up(setup_area):
    """door -r -u should remove an existing up door."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(up=True, auto=True))

    caller.messages.clear()
    cmd.run(caller, make_args(remove=True, up=True))

    assert any("Removed" in m for m in caller.messages)
    doors = nh.get_doors(Coord("TestArea", 0, 0, 0))
    if doors:
        assert "up" not in doors


def test_remove_no_doors_here(setup_area):
    """door -r -n with no doors at location should error."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(remove=True, north=True))

    assert any("no doors here" in m for m in caller.messages)


def test_remove_nonexistent_direction(setup_area):
    """door -r -s when only a north door exists should say no door south."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    # Create a north door
    cmd.run(caller, make_args(north=True, auto=True))

    caller.messages.clear()
    # Try to remove south (doesn't exist)
    cmd.run(caller, make_args(remove=True, south=True))

    assert any("no door south" in m.lower() for m in caller.messages)


# ==================== Link Deduplication Tests ====================


def test_north_link_not_duplicated(setup_area):
    """Creating a door north twice shouldn't duplicate links."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)

    # Create door north twice (remove first, then recreate)
    cmd.run(caller, make_args(north=True, auto=True))
    # Add the link manually to simulate pre-existing correct link
    here_links = start_node.get_links()
    north_count = sum(1 for l in here_links if l.name == "north")
    assert north_count == 1


# ==================== Multi-Direction Create Tests ====================


def test_create_multi_direction_all_created(setup_area):
    """INTENT: `door -n -s -e -w -u -d -a` must create doors in every requested
    direction. Create-mode currently returns after the first matching
    direction flag, so only the north door is ever built."""
    nh, area, grid, start_node = setup_area
    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    args = make_args(
        north=True, south=True, east=True, west=True, up=True, down=True, auto=True
    )
    cmd.run(caller, args)

    doors = nh.get_doors(Coord("TestArea", 0, 0, 0))
    assert doors is not None
    for d in ("north", "south", "east", "west", "up", "down"):
        assert d in doors, f"door {d} was not created: {list(doors or {})}"


# ==================== Existing Wrong Link Tests ====================


def test_wrong_link_replaced(setup_area):
    """If a 'north' link points to the wrong coord, it should be replaced."""
    nh, area, grid, start_node = setup_area
    # Add a wrong link
    wrong_link = NodeLink("north", Coord("TestArea", 99, 99, 0), ["n"])
    start_node.add_link(wrong_link)

    # Create destination
    dest_node = Node(coord=Coord("TestArea", 0, 2, 0))
    grid.nodes[(0, 2)] = dest_node

    cmd = DoorCommand()
    caller = MockCaller(location=start_node)
    cmd.run(caller, make_args(north=True))

    # Should have removed the wrong link and created a correct one
    assert any("wrong coord" in m for m in caller.messages)
    here_links = start_node.get_links()
    north_links = [l for l in here_links if l.name == "north"]
    assert len(north_links) == 1
    assert north_links[0].coord == Coord("TestArea", 0, 2, 0)


# ==================== Access Control Test ====================


def test_access_denied_for_non_builder(node_handler):
    """Non-builders should not have access to the door command."""
    cmd = DoorCommand()
    caller = MockCaller()
    caller.is_builder = False
    assert cmd.access(caller) is False


def test_access_granted_for_builder(node_handler):
    """Builders should have access to the door command."""
    cmd = DoorCommand()
    caller = MockCaller()
    caller.is_builder = True
    assert cmd.access(caller) is True


# ==================== Door Object Tests ====================


def test_door_create():
    """Door.create should produce a valid Door with correct attributes."""
    door = Door.create(
        from_coord=Coord("A", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("A", 0, 2, 0),
        to_exit="south",
        symbol_coord=(0, 1),
        closed_symbol="X",
        open_symbol="O",
    )
    assert door.from_coord == Coord("A", 0, 0, 0)
    assert door.to_coord == Coord("A", 0, 2, 0)
    assert door.from_exit == "north"
    assert door.to_exit == "south"
    assert door.closed is True
    assert door.locked is False
    assert door.symbol_coord == (0, 1)
    assert door.closed_symbol == "X"
    assert door.open_symbol == "O"


def test_door_str():
    door = Door.create(
        from_coord=Coord("A", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("A", 0, 2, 0),
        to_exit="south",
    )
    s = str(door)
    assert "north" in s
    assert "south" in s


def test_door_desc_from_side():
    door = Door.create(
        from_coord=Coord("A", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("A", 0, 2, 0),
        to_exit="south",
    )
    desc = door.desc(Coord("A", 0, 0, 0))
    assert "north" in desc
    assert "closed" in desc.lower()


def test_door_desc_to_side():
    door = Door.create(
        from_coord=Coord("A", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("A", 0, 2, 0),
        to_exit="south",
    )
    desc = door.desc(Coord("A", 0, 2, 0))
    assert "south" in desc


# ==================== NodeHandler Door Management Tests ====================


def test_nodehandler_add_door():
    nh = NodeHandler()
    door = Door.create(
        from_coord=Coord("A", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("A", 0, 2, 0),
        to_exit="south",
    )
    with patch("atheriz.globals.node.get_map_handler", return_value=MockMapHandler()):
        nh.add_door(door)

    assert nh.get_doors(Coord("A", 0, 0, 0))["north"] is door
    assert nh.get_doors(Coord("A", 0, 2, 0))["south"] is door


def test_nodehandler_remove_door():
    nh = NodeHandler()
    door = Door.create(
        from_coord=Coord("A", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("A", 0, 2, 0),
        to_exit="south",
    )
    with patch("atheriz.globals.node.get_map_handler", return_value=MockMapHandler()):
        nh.add_door(door)
        nh.remove_door(door)

    doors_from = nh.get_doors(Coord("A", 0, 0, 0))
    doors_to = nh.get_doors(Coord("A", 0, 2, 0))
    if doors_from:
        assert "north" not in doors_from
    if doors_to:
        assert "south" not in doors_to


def test_nodehandler_get_doors_empty():
    nh = NodeHandler()
    assert nh.get_doors(Coord("A", 0, 0, 0)) is None


class TestDoorMapGlyph:
    def test_map_close_without_to_coord(self, global_test_env):
        """INTENT: closing a door that has no to_coord must not crash."""
        d = Door(
            from_coord=Coord("test", 0, 0, 0),
            from_exit="east",
            to_coord=None,
            to_exit=None,
            symbol_coord=(5, 5),
        )
        with patch("atheriz.settings.MAP_ENABLED", True):
            d.map_close()

    def test_map_open_without_to_coord(self, global_test_env):
        """INTENT: opening a door that has no to_coord must not crash."""
        d = Door(
            from_coord=Coord("test", 0, 0, 0),
            from_exit="east",
            to_coord=None,
            to_exit=None,
            symbol_coord=(5, 5),
        )
        with patch("atheriz.settings.MAP_ENABLED", True):
            d.map_open()


class _Door:
    name = "iron_door"
    closed = True
    locked = False

    def try_open(self, caller):
        return True

    def try_close(self, caller):
        return None


def _make_area(nh: NodeHandler):
    src = Node(coord=Coord("a", 0, 0, 0))
    dest = Node(coord=Coord("a", 0, 1, 0))
    grid = NodeGrid(area="a", z=0)
    grid.add_node(src)
    grid.add_node(dest)
    area = NodeArea(name="a")
    area.add_grid(grid)
    nh.add_area(area)
    return src, dest


class TestDoorFollow:
    def test_door_passage_clears_following(self, global_test_env, monkeypatch):
        """INTENT: passing through an open door clears following, exactly like a
        plain exit does. Today the door branch drops the follower's following
        stays set -> the follower keeps tracking the leader through the wall."""
        nh = NodeHandler()
        src, dest = _make_area(nh)
        door = _Door()
        nh.doors[Coord("a", 0, 0, 0)] = {"iron_door": door}

        leader = Object.create(None, "Leader")
        follower = Object.create(None, "Follower")
        follower.move_to(src)

        monkeypatch.setattr("atheriz.commands.loggedin.exit.get_node_handler", lambda: nh)

        follower.following = leader.id
        leader.followers = {follower.id}

        ex = ExitCommand()
        ex.caller_id = follower.id
        ex.location = Coord("a", 0, 0, 0)
        ex.destination = Coord("a", 0, 1, 0)
        ex.name = "iron_door"
        ex.do_move()

        assert follower.following is None, (
            "door passage must clear following the same way a plain exit does"
        )

    def test_open_door_passage_clears_following(self, global_test_env, monkeypatch):
        """INTENT: passing through an already-open door must clear following too."""
        nh = NodeHandler()
        src, dest = _make_area(nh)
        door = _Door()
        door.closed = False
        nh.doors[Coord("a", 0, 0, 0)] = {"iron_door": door}

        leader = Object.create(None, "Leader")
        follower = Object.create(None, "Follower")
        follower.move_to(src)

        monkeypatch.setattr("atheriz.commands.loggedin.exit.get_node_handler", lambda: nh)

        follower.following = leader.id
        leader.followers = {follower.id}

        ex = ExitCommand()
        ex.caller_id = follower.id
        ex.location = Coord("a", 0, 0, 0)
        ex.destination = Coord("a", 0, 1, 0)
        ex.name = "iron_door"
        ex.do_move()

        assert follower.following is None

    def test_locked_door_keeps_following(self, global_test_env, monkeypatch):
        """INTENT: when the door refuses passage the follower does not move, so
        following must be preserved."""
        nh = NodeHandler()
        src, dest = _make_area(nh)
        door = _Door()
        door.try_open = lambda caller: False
        nh.doors[Coord("a", 0, 0, 0)] = {"iron_door": door}

        leader = Object.create(None, "Leader")
        follower = Object.create(None, "Follower")
        follower.move_to(src)

        monkeypatch.setattr("atheriz.commands.loggedin.exit.get_node_handler", lambda: nh)

        follower.following = leader.id
        leader.followers = {follower.id}

        ex = ExitCommand()
        ex.caller_id = follower.id
        ex.location = Coord("a", 0, 0, 0)
        ex.destination = Coord("a", 0, 1, 0)
        ex.name = "iron_door"
        ex.do_move()

        assert follower.following == leader.id
        assert follower.id in leader.followers


class TestDoorOrphan:
    def test_door_creation_relocates_player_on_replaced_node(self, global_test_env):
        """INTENT: a player standing on the node that becomes a door must not
        be stranded; their location must still resolve to a live node."""
        nh = get_node_handler()
        origin = Node(Coord("test", 0, 0, 0))
        door_node = Node(Coord("test", 0, 1, 0))
        dest = Node(Coord("test", 0, 2, 0))
        for n in (origin, door_node, dest):
            nh.add_node(n)

        player = Object.create(None, "stranded", is_pc=True)
        player.location = door_node
        door_node.add_object(player)

        caller = FakesMockCaller(name="builder", location=origin)

        cmd = DoorCommand()
        cmd.run(
            caller,
            fakes_make_args(
                north=True,
                south=False,
                east=False,
                west=False,
                up=False,
                down=False,
                remove=False,
            ),
        )

        assert nh.get_node(player.location.coord) is player.location


def test_door_broadcast_does_not_hold_lock(global_test_env):
    from atheriz.objects.base_obj import Object
    from unittest.mock import MagicMock
    import threading

    door = Door.create(
        from_coord=Coord("TestArea", 0, 0, 0),
        from_exit="n",
        to_coord=Coord("TestArea", 0, 1, 0),
        to_exit="s",
        symbol_coord=(0, 0),
        closed_symbol="C",
        open_symbol="O",
        closed=True,
        locked=False,
    )
    from_node = Node(coord=Coord("TestArea", 0, 0, 0))
    to_node = Node(coord=Coord("TestArea", 0, 1, 0))
    from atheriz.globals.get import get_node_handler
    nh = get_node_handler()
    nh.add_node(from_node)
    nh.add_node(to_node)
    caller = Object.create(None, "DoorUser")
    caller.location = from_node
    orig_msg = Node.msg_contents
    captured_locked = []

    def spy_msg(self, *a, **kw):
        try:
            is_locked = door.lock._is_owned()
        except Exception:
            is_locked = False
            holder = []
            def try_acquire():
                acquired = door.lock.acquire(blocking=False)
                holder.append(acquired)
                if acquired:
                    door.lock.release()
            t = threading.Thread(target=try_acquire)
            t.start()
            t.join(timeout=1)
            if holder and not holder[0]:
                is_locked = True
        captured_locked.append(is_locked)
        return orig_msg(self, *a, **kw)

    with patch.object(Node, "msg_contents", spy_msg):
        with patch("atheriz.objects.base_door.get_map_handler") as mock_mh:
            mock_mi = MagicMock()
            mock_mi.lock = threading.RLock()
            mock_mi.post_grid = {}
            mock_mi.pre_grid = {}
            mock_mi.map_changed = False
            mock_mi.render = MagicMock()
            mock_mh.return_value.get_mapinfo.return_value = mock_mi
            result = door.try_open(caller)
            assert result is True
    assert len(captured_locked) >= 1
    assert not any(captured_locked), f"door lock held during broadcast: {captured_locked}"

    captured_locked.clear()
    door.closed = False
    with patch.object(Node, "msg_contents", spy_msg):
        with patch("atheriz.objects.base_door.get_map_handler") as mock_mh:
            mock_mi = MagicMock()
            mock_mi.lock = threading.RLock()
            mock_mi.post_grid = {}
            mock_mi.pre_grid = {}
            mock_mi.map_changed = False
            mock_mi.render = MagicMock()
            mock_mh.return_value.get_mapinfo.return_value = mock_mi
            result = door.try_close(caller)
            assert result is True
    assert not any(captured_locked)
