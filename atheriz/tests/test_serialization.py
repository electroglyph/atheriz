import pytest
import dill
import os
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel
from atheriz.commands.base_cmd import Command
from atheriz.objects.nodes import Node, NodeLink, NodeGrid, NodeArea, Transition, Door
from atheriz.singletons.map import LegendEntry, MapInfo

class CustomData:
    """A small custom class to test reference serialization."""
    def __init__(self, value, nested=None):
        self.value = value
        self.nested = nested

    def __eq__(self, other):
        if not isinstance(other, CustomData):
            return False
        return self.value == other.value and self.nested == other.nested

def assert_serialization(obj):
    """Helper to assert serialization and deserialization using dill."""
    serialized = dill.dumps(obj)
    deserialized = dill.loads(serialized)
    
    # Check that all attributes from __getstate__ are preserved
    state = obj.__getstate__()
    
    # We compare the dictionary of the state, but we need to handle non-equatable items if any
    # Objects might have RLock which are popped in __getstate__ or recreated in __setstate__
    # 'access' is a bound method which fails equality check.
    # 'locks' contains callables which might also fail.
    skip_keys = ["lock", "lock2", "lock3", "access", "locks", "_parser"]
    
    for key, value in state.items():
        if key in skip_keys:
            continue
        # Use object.__getattribute__ to bypass thread-safety wrapper which might try to use a missing lock
        assert object.__getattribute__(deserialized, key) == value, f"Attribute {key} mismatch"
    
    return deserialized

def test_object_serialization():
    obj = Object()
    obj.name = "Test Object"
    obj.desc = "A mysterious test object."
    obj.custom_ref = CustomData("some value", CustomData(123))
    obj.id = 100
    
    deserialized = assert_serialization(obj)
    assert object.__getattribute__(deserialized, "name") == obj.name
    assert object.__getattribute__(deserialized, "custom_ref").value == "some value"
    assert object.__getattribute__(deserialized, "custom_ref").nested.value == 123
    assert isinstance(object.__getattribute__(deserialized, "custom_ref"), CustomData)

def test_account_serialization():
    acc = Account()
    acc.id = 200
    acc.name = "TestUser"
    acc.password = "hashed_pw"
    acc.characters = [1, 2, 3]
    acc.metadata = CustomData("meta")
    
    deserialized = assert_serialization(acc)
    assert object.__getattribute__(deserialized, "name") == acc.name
    assert object.__getattribute__(deserialized, "characters") == [1, 2, 3]
    assert object.__getattribute__(deserialized, "metadata").value == "meta"

def test_channel_serialization():
    chan = Channel()
    chan.id = 300
    chan.name = "OOC"
    chan.desc = "Out of Character"
    chan.listeners = {1: None, 2: None} # listeners are IDs to Objects, but here we just test data
    chan.custom_data = CustomData("chan_data")
    
    deserialized = assert_serialization(chan)
    assert object.__getattribute__(deserialized, "name") == chan.name
    assert object.__getattribute__(deserialized, "custom_data").value == "chan_data"

def test_command_serialization():
    class MyCommand(Command):
        key = "testcmd"
        def __init__(self):
            super().__init__()
            self.custom_attr = CustomData("cmd_attr")
            
    cmd = MyCommand()
    # Command.__getstate__ is not explicitly defined in base_cmd.py but it uses default behavior
    # Actually, Command has self._parser which it might want to pop, but base_cmd.py shows:
    # def __setstate__(self, state):
    #     self.__dict__.update(state)
    #     if self.use_parser: ...
    
    serialized = dill.dumps(cmd)
    deserialized = dill.loads(serialized)
    
    assert object.__getattribute__(deserialized, "key") == "testcmd"
    assert object.__getattribute__(deserialized, "custom_attr").value == "cmd_attr"

def test_node_serialization():
    node = Node(coord=("limbo", 0, 0, 0), desc="Empty space")
    node.theme = "void"
    node.data = {"key": "val", "custom": CustomData("node_data")}
    
    deserialized = assert_serialization(node)
    assert object.__getattribute__(deserialized, "coord") == ("limbo", 0, 0, 0)
    assert object.__getattribute__(deserialized, "data")["custom"].value == "node_data"

def test_nodelink_serialization():
    link = NodeLink(name="North", coord=("forest", 0, 1, 0), aliases=["n"])
    link.meta = CustomData("link_meta")
    
    deserialized = assert_serialization(link)
    assert object.__getattribute__(deserialized, "name") == "North"
    assert object.__getattribute__(deserialized, "meta").value == "link_meta"

def test_nodegrid_serialization():
    grid = NodeGrid(area="forest", z=0)
    node = Node(coord=("forest", 0, 0, 0))
    grid.nodes[(0, 0)] = node
    grid.data = {"custom": CustomData("grid_data")}
    
    deserialized = assert_serialization(grid)
    assert object.__getattribute__(deserialized, "area") == "forest"
    assert object.__getattribute__(deserialized, "data")["custom"].value == "grid_data"
    assert (0, 0) in object.__getattribute__(deserialized, "nodes")

def test_nodearea_serialization():
    area = NodeArea(name="forest")
    grid = NodeGrid(area="forest", z=0)
    area.grids[0] = grid
    area.data = {"custom": CustomData("area_data")}
    
    deserialized = assert_serialization(area)
    assert object.__getattribute__(deserialized, "name") == "forest"
    assert object.__getattribute__(deserialized, "data")["custom"].value == "area_data"
    assert 0 in object.__getattribute__(deserialized, "grids")

def test_transition_serialization():
    trans = Transition(from_coord=("a", 0, 0, 0), to_coord=("b", 0, 0, 0), from_link="path")
    trans.custom = CustomData("trans_data")
    # Transition has RLock in __setstate__ but not explicitly in __init__ or __getstate__?
    # Actually Transition.__setstate__ adds self.lock = RLock()
    
    serialized = dill.dumps(trans)
    deserialized = dill.loads(serialized)
    
    assert object.__getattribute__(deserialized, "from_link") == "path"
    assert object.__getattribute__(deserialized, "custom").value == "trans_data"

def test_door_serialization():
    door = Door(
        from_coord=("room1", 1, 0, 0),
        from_exit="east",
        to_coord=("room2", 2, 0, 0),
        to_exit="west",
        closed=True,
        locked=False
    )
    door.custom = CustomData("door_data")
    
    # Door uses AtomicFlag/AtomicInt which are handled in __getstate__/__setstate__
    deserialized = assert_serialization(door)
    assert object.__getattribute__(deserialized, "from_exit") == "east"
    assert object.__getattribute__(deserialized, "custom").value == "door_data"
    assert object.__getattribute__(deserialized, "is_closed") == True
    assert object.__getattribute__(deserialized, "is_locked") == False

def test_legendentry_serialization():
    entry = LegendEntry(symbol="T", desc="A Tree", coord=(10, 20))
    entry.custom = CustomData("legend_data")
    
    # LegendEntry doesn't have __getstate__ defined (it was commented out)
    # So it uses default behavior.
    serialized = dill.dumps(entry)
    deserialized = dill.loads(serialized)
    
    assert object.__getattribute__(deserialized, "symbol") == "T"
    assert object.__getattribute__(deserialized, "custom").value == "legend_data"

def test_mapinfo_serialization():
    mi = MapInfo(name="The Forest")
    mi.pre_grid = {(0, 0): "T"}
    mi.legend_entries = [LegendEntry(symbol="T", desc="Tree")]
    mi.custom = CustomData("map_data")
    
    deserialized = assert_serialization(mi)
    assert object.__getattribute__(deserialized, "name") == "The Forest"
    assert object.__getattribute__(deserialized, "pre_grid")[(0, 0)] == "T"
    assert object.__getattribute__(deserialized, "custom").value == "map_data"
    assert len(object.__getattribute__(deserialized, "legend_entries")) == 1
    assert object.__getattribute__(deserialized, "legend_entries")[0].symbol == "T"

def test_resolve_relations():
    from atheriz.singletons import objects as obj_singleton
    from atheriz.singletons.get import get_node_handler
    
    # Setup state
    obj_singleton._ALL_OBJECTS.clear()
    
    # 1. Create a Target Object (ID 500)
    target_obj = Object()
    target_obj.id = 500
    obj_singleton.add_object(target_obj)
    
    # 2. Create a Target Node
    nav_node = Node(coord=("test_area", 1, 1, 1))
    nav_node.id = 501
    
    # Setup NodeHandler
    nh = get_node_handler()
    if "test_area" not in nh.areas:
        nh.areas["test_area"] = NodeArea("test_area")
    
    grid = NodeGrid("test_area", 1)
    grid.nodes[(1, 1)] = nav_node
    nh.areas["test_area"].grids[1] = grid
    
    # 3. Create a Source Object that links to both
    source_obj = Object()
    source_obj.id = 502
    source_obj.location = nav_node
    source_obj.home = target_obj
    
    # Serialization (Pass 1 of Saving)
    serialized = dill.dumps(source_obj)
    
    # Deserialization (Pass 1 of Loading)
    deserialized = dill.loads(serialized)
    
    # ASSERT PASS 1 STATE: Raw data restoration only
    assert object.__getattribute__(deserialized, "location") == ("test_area", 1, 1, 1)
    assert object.__getattribute__(deserialized, "home") == 500
    
    # Resolution (Pass 2 of Loading)
    deserialized.resolve_relations()
    
    # ASSERT PASS 2 STATE: Relations successfully re-linked
    assert object.__getattribute__(deserialized, "location") is nav_node
    assert object.__getattribute__(deserialized, "home") is target_obj
