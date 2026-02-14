import pytest
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
# from atheriz.utils import get_import_path
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.commands.cmdset import CmdSet
from atheriz.singletons import objects as obj_singleton
from atheriz.singletons.node import (
    _serialize_areas,
    _deserialize_areas,
    _serialize_transitions,
    _deserialize_transitions,
    _serialize_doors,
    _deserialize_doors,
)
from atheriz.singletons.map import MapInfo, LegendEntry
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink, Door, Transition

def get_import_path(obj: object) -> str:
    return obj.__module__ + "." + obj.__class__.__name__



@pytest.fixture(autouse=True)
def cleanup():
    obj_singleton._ALL_OBJECTS.clear()


def assert_same_state(obj1, obj2):
    """
    Assert that two objects have the same state.
    For primitives, check equality.
    For others, check existence (not None).
    """
    state1 = obj1.__dict__
    state2 = obj2.__dict__

    # Check key equality
    assert (
        state1.keys() == state2.keys()
    ), f"Keys mismatch\nOriginal: {state1.keys()}\nRestored: {state2.keys()}"

    for k, v1 in state1.items():
        v2 = state2[k]
        if isinstance(v1, (int, str, float, bool, type(None), tuple)):
            assert v1 == v2, f"Attribute '{k}' mismatch: {v1} != {v2}"
        else:
            # For complex types, just ensure if original had it, restored has it (is not None)
            if v1 is not None:
                assert (
                    v2 is not None
                ), f"Attribute '{k}' is None in restored object but was present in original"


def test_node_serialization():
    node = Node(coord=("area", 1, 2, 3), desc="Test Node")
    node.add_link(NodeLink(name="north", coord=("area", 1, 3, 3)))

    state = node.__getstate__()

    new_node = Node()
    new_node.__setstate__(state)

    node.__import_path__ = get_import_path(node)
    assert_same_state(node, new_node)

    assert new_node.coord == ("area", 1, 2, 3)
    assert new_node.desc == "Test Node"
    assert new_node.links is not None
    assert len(new_node.links) == 1
    assert new_node.links[0].name == "north"
    assert new_node.links[0].coord == ("area", 1, 3, 3)


def test_node_serialization_with_locks():
    """Test that locks on Nodes are serialized and deserialized correctly."""
    node = Node(coord=("area", 1, 2, 3), desc="Locked Node")

    # Add locks
    node.add_lock(
        "enter", lambda x: getattr(x, "is_builder", False) or getattr(x, "is_superuser", False)
    )
    node.add_lock("view", lambda x: True)

    state = node.__getstate__()

    new_node = Node()
    new_node.__setstate__(state)

    # Verify lock structure
    assert "enter" in new_node.locks
    assert "view" in new_node.locks
    assert len(new_node.locks["enter"]) == 1

    # Verify locks function
    # Mock an accessor object
    class MockAccessor:
        def __init__(self, is_builder=False, is_superuser=False):
            self.is_builder = is_builder
            self.is_superuser = is_superuser

    builder = MockAccessor(is_builder=True)
    player = MockAccessor(is_builder=False)

    assert new_node.access(builder, "enter") is True
    assert new_node.access(player, "enter") is False
    assert new_node.access(player, "view") is True


def test_nodegrid_serialization():
    grid = NodeGrid(z=1)
    node = Node(coord=("area", 1, 1, 1), desc="Grid Node")
    grid.nodes[(1, 1)] = node

    state = grid.__getstate__()

    new_grid = NodeGrid()
    new_grid.__setstate__(state)

    grid.__import_path__ = get_import_path(grid)
    assert_same_state(grid, new_grid)

    assert new_grid.z == 1
    assert (1, 1) in new_grid.nodes
    # Verify the node inside was restored
    restored_node = new_grid.nodes[(1, 1)]
    assert restored_node.coord == ("area", 1, 1, 1)
    assert restored_node.desc == "Grid Node"


def test_nodearea_serialization():
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    node = Node(coord=("TestArea", 0, 0, 0), desc="Area Node")
    grid.nodes[(0, 0)] = node
    area.grids[0] = grid

    state = area.__getstate__()

    new_area = NodeArea()
    new_area.__setstate__(state)

    area.__import_path__ = get_import_path(area)
    assert_same_state(area, new_area)

    assert new_area.name == "TestArea"
    assert 0 in new_area.grids

    restored_grid = new_area.grids[0]
    assert restored_grid.z == 0
    assert (0, 0) in restored_grid.nodes
    assert restored_grid.nodes[(0, 0)].desc == "Area Node"


def test_account_serialization():
    acc = Account.create("TestUser", "password")
    acc.logged_in = True

    state = acc.__getstate__()

    new_acc = Account()
    new_acc.__setstate__(state)

    acc.__import_path__ = get_import_path(acc)
    assert_same_state(acc, new_acc)

    assert new_acc.name == "TestUser"
    assert new_acc.check_password("password")
    assert new_acc.logged_in == True
    assert new_acc.id == acc.id


class SimpleObject(Object):
    pass


def test_object_serialization():
    obj = SimpleObject()
    obj.internal_cmdset = CmdSet()
    obj.external_cmdset = CmdSet()
    obj.name = "TestObject"
    obj.desc = "Description"

    state = obj.__getstate__()

    new_obj = SimpleObject()
    new_obj.__setstate__(state)

    obj.__import_path__ = get_import_path(obj)
    assert_same_state(obj, new_obj)

    assert new_obj.name == "TestObject"
    assert new_obj.desc == "Description"
    assert new_obj.internal_cmdset is not None
    assert new_obj.external_cmdset is not None


def test_object_serialization_with_locks():
    """Test that locks are serialized and deserialized correctly."""
    obj = SimpleObject()
    obj.name = "LockedObject"

    # Add locks with lambda callables
    # Note: Multiple locks on same name = AND logic (all must pass)
    obj.add_lock("control", lambda x: x.is_builder or x.is_superuser)
    obj.add_lock("view", lambda x: True)
    obj.add_lock("edit", lambda x: x.privilege_level >= 3)

    state = obj.__getstate__()

    new_obj = SimpleObject()
    new_obj.__setstate__(state)

    # Verify lock structure is preserved
    assert "control" in new_obj.locks
    assert "view" in new_obj.locks
    assert "edit" in new_obj.locks
    assert len(new_obj.locks["control"]) == 1
    assert len(new_obj.locks["view"]) == 1
    assert len(new_obj.locks["edit"]) == 1

    # Verify locks still function correctly
    accessor = SimpleObject()
    accessor.privilege_level = 3  # builder
    accessor.quelled = False

    # Test that the deserialized locks work
    assert new_obj.access(accessor, "view") is True
    assert new_obj.access(accessor, "edit") is True
    assert new_obj.access(accessor, "control") is True  # is_builder returns True for priv >= 3


def test_nodehandler_serialize_areas():
    area = NodeArea(name="TestAreaHandler")
    areas = {"TestAreaHandler": area}

    serialized = _serialize_areas(areas)
    deserialized = _deserialize_areas(serialized)

    assert "TestAreaHandler" in deserialized
    assert deserialized["TestAreaHandler"].name == "TestAreaHandler"


def test_nodehandler_serialize_transitions():
    t = Transition(from_coord=("Area1", 0, 0, 0), to_coord=("Area2", 0, 0, 0), from_link="north")
    # Key is destination coordinate
    transitions = {("Area2", 0, 0, 0): t}

    serialized = _serialize_transitions(transitions)
    deserialized = _deserialize_transitions(serialized)

    key = ("Area2", 0, 0, 0)
    assert key in deserialized
    new_t = deserialized[key]
    assert new_t.from_coord == ("Area1", 0, 0, 0)
    assert new_t.to_coord == ("Area2", 0, 0, 0)
    assert new_t.from_link == "north"


def test_nodehandler_serialize_doors():
    door = Door(
        from_coord=("Area1", 0, 0, 0),
        to_coord=("Area2", 0, 0, 0),
        from_exit="north",
        to_exit="south",
    )

    # Structure based on NodeHandler.doors: {coord: {exit_name: Door}}
    coord = ("Area1", 0, 0, 0)
    doors = {coord: {"north": door}}

    serialized = _serialize_doors(doors)
    deserialized = _deserialize_doors(serialized)

    assert coord in deserialized
    assert "north" in deserialized[coord]
    new_door = deserialized[coord]["north"]

    assert new_door.from_coord == ("Area1", 0, 0, 0)
    assert new_door.to_coord == ("Area2", 0, 0, 0)
    assert new_door.from_exit == "north"
    assert new_door.to_exit == "south"


def test_mapinfo_serialization():
    # Create a MapInfo object with new API
    legend_entry = LegendEntry(symbol="x", desc="test_legend", coord=(0, 0))
    map_info = MapInfo(
        name="TestMap",
        pre_grid={(0, 0): ".", (1, 0): "#", (0, 1): ".", (1, 1): "#"},
        legend_entries=[legend_entry],
    )

    # Simulate runtime state that shouldn't be serialized or should be re-initialized
    map_info.objects[1] = SimpleObject()
    map_info.listeners[2] = SimpleObject()

    # Get state
    state = map_info.__getstate__()

    # Create empty object and restore state
    new_map_info = MapInfo("dummy")
    new_map_info.__setstate__(state)

    map_info.__import_path__ = get_import_path(map_info)
    assert_same_state(map_info, new_map_info)

    # Verify attributes
    assert new_map_info.name == "TestMap"
    assert new_map_info.pre_grid == {(0, 0): ".", (1, 0): "#", (0, 1): ".", (1, 1): "#"}

    # Verify legend entries
    assert len(new_map_info.legend_entries) == 1
    new_entry = new_map_info.legend_entries[0]
    assert new_entry.symbol == "x"
    assert new_entry.desc == "test_legend"
    assert new_entry.coord == (0, 0)

    # Verify runtime attributes are reset/empty
    assert new_map_info.objects == {}
    assert new_map_info.listeners == {}
    assert new_map_info.lock is not None
