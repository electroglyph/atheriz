import pytest
from unittest.mock import MagicMock, patch
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.singletons.node import NodeHandler
from atheriz.objects.base_door import Door
from atheriz.pathfind import astar

class MockMapInfo:
    def update_grid(self, coord, symbol):
        pass

    def render(self, force=False):
        pass

class MockMapHandler:
    def get_mapinfo(self, area, z):
        return MockMapInfo()

@pytest.fixture
def node_handler():
    nh = NodeHandler()
    with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
         patch("atheriz.objects.nodes.get_node_handler", return_value=nh), \
         patch("atheriz.objects.base_door.get_node_handler", return_value=nh), \
         patch("atheriz.singletons.node.get_map_handler", return_value=MockMapHandler()), \
         patch("atheriz.objects.base_door.get_map_handler", return_value=MockMapHandler()):
        yield nh

@pytest.fixture
def setup_pathfind_area(node_handler):
    area = NodeArea(name="PathArea")
    grid = NodeGrid(area="PathArea", z=0)
    
    # We create nodes for a small map to test pathfinding and door logic:
    # y=1: n4(0,1) - n5(1,1) - n6(2,1)
    #        |                   |
    # y=0: n1(0,0) - n2(1,0) - n3(2,0)
    # The direct path n1 -> n2 -> n3 has distance 2
    # The detour path n1 -> n4 -> n5 -> n6 -> n3 has distance 4
    
    nodes = {}
    for x in (0, 1, 2):
        for y in (0, 1):
            n = Node(coord=("PathArea", x, y, 0))
            nodes[(x, y)] = n
            grid.nodes[(x, y)] = n
            
    # Add links for the direct path (y=0)
    nodes[(0,0)].add_link(NodeLink("east", ("PathArea", 1, 0, 0), ["e"]))
    nodes[(1,0)].add_link(NodeLink("west", ("PathArea", 0, 0, 0), ["w"]))
    
    nodes[(1,0)].add_link(NodeLink("east", ("PathArea", 2, 0, 0), ["e"]))
    nodes[(2,0)].add_link(NodeLink("west", ("PathArea", 1, 0, 0), ["w"]))
    
    # Add links for the detour path (via y=1)
    nodes[(0,0)].add_link(NodeLink("north", ("PathArea", 0, 1, 0), ["n"]))
    nodes[(0,1)].add_link(NodeLink("south", ("PathArea", 0, 0, 0), ["s"]))
    
    nodes[(0,1)].add_link(NodeLink("east", ("PathArea", 1, 1, 0), ["e"]))
    nodes[(1,1)].add_link(NodeLink("west", ("PathArea", 0, 1, 0), ["w"]))
    
    nodes[(1,1)].add_link(NodeLink("east", ("PathArea", 2, 1, 0), ["e"]))
    nodes[(2,1)].add_link(NodeLink("west", ("PathArea", 1, 1, 0), ["w"]))
    
    nodes[(2,1)].add_link(NodeLink("south", ("PathArea", 2, 0, 0), ["s"]))
    nodes[(2,0)].add_link(NodeLink("north", ("PathArea", 2, 1, 0), ["n"]))

    area.add_grid(grid)
    node_handler.add_area(area)
    
    return node_handler, area, grid, nodes

def test_astar_no_doors(setup_pathfind_area):
    """Pathfinding goes the shortest route when there are no doors."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    success, path, closed = astar(start, end)
    assert success is True
    # Path should be n1 -> n2 -> n3, so length 3
    assert len(path) == 3
    assert path[0] == start
    assert path[1] == nodes[(1,0)]
    assert path[2] == end

def test_astar_open_door(setup_pathfind_area):
    """Pathfinding goes through open doors."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    # Door between (0,0) and (1,0)
    door = Door.create(
        from_coord=("PathArea", 0, 0, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 0, 0),
        to_exit="west",
        closed=False,
    )
    nh.add_door(door)
    
    # Caller is required to check doors, though if door is open it might pass anyway
    caller = MagicMock()
    success, path, closed = astar(start, end, caller=caller)
    
    assert success is True
    assert len(path) == 3
    assert path[1] == nodes[(1,0)]

def test_astar_closed_unlocked_door_can_open(setup_pathfind_area):
    """Pathfinding goes through closed doors if caller can open them."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    door = Door.create(
        from_coord=("PathArea", 0, 0, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 0, 0),
        to_exit="west",
        closed=True,
        locked=False
    )
    nh.add_door(door)
    
    caller = MagicMock()
    # Mock access to return True for "open"
    door.access = MagicMock(return_value=True)
    
    success, path, closed = astar(start, end, caller=caller)
    
    assert success is True
    assert len(path) == 3
    assert path[1] == nodes[(1,0)]
    door.access.assert_called_with(caller, "open")

def test_astar_closed_unlocked_door_cannot_open_routes_around(setup_pathfind_area):
    """Pathfinding routes around closed doors if caller cannot open them."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    door = Door.create(
        from_coord=("PathArea", 0, 0, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 0, 0),
        to_exit="west",
        closed=True,
        locked=False
    )
    nh.add_door(door)
    
    caller = MagicMock()
    # Mock access to return False for "open"
    door.access = MagicMock(return_value=False)
    
    success, path, closed = astar(start, end, caller=caller)
    
    assert success is True
    # Should route around: n1 -> n4 -> n5 -> n6 -> n3 
    # That is (0,0) -> (0,1) -> (1,1) -> (2,1) -> (2,0)
    assert len(path) == 5
    assert path[1] == nodes[(0,1)]
    assert path[2] == nodes[(1,1)]
    assert path[3] == nodes[(2,1)]

def test_astar_locked_door_can_unlock(setup_pathfind_area):
    """Pathfinding goes through locked doors if caller can open and unlock them."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    door = Door.create(
        from_coord=("PathArea", 0, 0, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 0, 0),
        to_exit="west",
        closed=True,
        locked=True
    )
    nh.add_door(door)
    
    caller = MagicMock()
    # Mock access to return True for both "open" and "unlock"
    door.access = MagicMock(return_value=True)
    
    success, path, closed = astar(start, end, caller=caller)
    
    assert success is True
    assert len(path) == 3
    assert path[1] == nodes[(1,0)]

def test_astar_locked_door_cannot_unlock_routes_around(setup_pathfind_area):
    """Pathfinding routes around locked doors if caller cannot unlock them."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    door = Door.create(
        from_coord=("PathArea", 0, 0, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 0, 0),
        to_exit="west",
        closed=True,
        locked=True
    )
    nh.add_door(door)
    
    caller = MagicMock()
    # Mock access to return True for "open" but False for "unlock"
    def access_mock(c, access_type):
        if access_type == "open":
            return True
        if access_type == "unlock":
            return False
        return True
        
    door.access = MagicMock(side_effect=access_mock)
    
    success, path, closed = astar(start, end, caller=caller)
    
    assert success is True
    # Should route around because it cannot unlock
    assert len(path) == 5
    assert path[1] == nodes[(0,1)]

def test_astar_blocked_completely(setup_pathfind_area):
    """Pathfinding fails if there is no valid unblocked route."""
    nh, area, grid, nodes = setup_pathfind_area
    start = nodes[(0,0)]
    end = nodes[(2,0)]
    
    # Block direct route
    door1 = Door.create(
        from_coord=("PathArea", 0, 0, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 0, 0),
        to_exit="west",
        closed=True,
        locked=True
    )
    nh.add_door(door1)
    
    # Block detour route at (0,1) -> (1,1)
    door2 = Door.create(
        from_coord=("PathArea", 0, 1, 0),
        from_exit="east",
        to_coord=("PathArea", 1, 1, 0),
        to_exit="west",
        closed=True,
        locked=True
    )
    nh.add_door(door2)
    
    caller = MagicMock()
    door1.access = MagicMock(return_value=False)
    door2.access = MagicMock(return_value=False)
    
    success, path, closed = astar(start, end, caller=caller)
    
    assert success is False
