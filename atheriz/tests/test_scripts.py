import pytest
import tempfile
import shutil
from atheriz import settings
from atheriz.database_setup import do_setup
from atheriz.singletons import get as singletons_get
from atheriz.singletons.objects import _ALL_OBJECTS, save_objects, load_objects
import atheriz.database_setup as db_mod
from atheriz.singletons import objects as obj_singleton


from atheriz.objects.base_obj import Object, hookable
from atheriz.objects.base_script import Script, before, after, replace
from atheriz.objects.nodes import Node




class DummyObj(Object):
    log: list = []

    def __init__(self):
        super().__init__()
        self.log = []

    @hookable
    def at_test_hook(self, arg1, kwarg1=None):
        self.log.append(f"at_test_hook: {arg1}, {kwarg1}")
        return "original_result"


class DummyNode(Node):
    log: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = []

    @hookable
    def at_test_hook(self, arg1, kwarg1=None):
        self.log.append(f"at_test_hook: {arg1}, {kwarg1}")
        return "original_result"


class DummyBeforeScript(Script):
    @before
    def at_test_hook(self, arg1, kwarg1=None):
        self.child.log.append(f"before: {arg1}, {kwarg1}")


class DummyAfterScript(Script):
    @after
    def at_test_hook(self, arg1, kwarg1=None):
        self.child.log.append(f"after: {arg1}, {kwarg1}")
        return "after_result"


class DummyReplaceScript(Script):
    @replace
    def at_test_hook(self, arg1, kwarg1=None):
        self.child.log.append(f"replace: {arg1}, {kwarg1}")
        return "replace_result"


class DummyUnmarkedScript(Script):
    def at_test_hook(self, arg1, kwarg1=None):
        pass


def test_add_remove_script():
    obj = DummyObj.create(None, "TestObj")
    script = DummyBeforeScript()
    script.id = 101

    obj.add_script(script)
    assert script.id in obj.scripts
    assert len(obj.hooks.get("at_test_hook", set())) == 1

    obj.remove_script(script)
    assert script.id not in obj.scripts
    assert len(obj.hooks.get("at_test_hook", set())) == 0


def test_before_hook():
    obj = DummyObj.create(None, "TestObj")
    script = DummyBeforeScript()
    script.id = 102
    obj.add_script(script)

    res = obj.at_test_hook("v1", kwarg1="v2")
    assert obj.log == ["before: v1, v2", "at_test_hook: v1, v2"]
    assert res == "original_result"


def test_after_hook():
    obj = DummyObj.create(None, "TestObj")
    script = DummyAfterScript()
    script.id = 103
    obj.add_script(script)

    res = obj.at_test_hook("v3", kwarg1="v4")
    assert obj.log == ["at_test_hook: v3, v4", "after: v3, v4"]
    assert res == "after_result"


def test_replace_hook():
    obj = DummyObj.create(None, "TestObj")
    script = DummyReplaceScript()
    script.id = 104
    obj.add_script(script)

    res = obj.at_test_hook("v5", kwarg1="v6")
    assert obj.log == ["replace: v5, v6"]
    assert res == "replace_result"


def test_unmarked_hook_raises_error():
    obj = DummyObj.create(None, "TestObj")
    script = DummyUnmarkedScript()
    script.id = 105
    obj.add_script(script)

    with pytest.raises(ValueError) as exc:
        obj.at_test_hook("foo", kwarg1="bar")
    assert "has hooks but none are marked" in str(exc.value)

def test_script_at_install():
    obj = DummyObj.create(None, "TestObj")
    script = DummyBeforeScript.create(None, "TestScript")
    
    # We will test that at_install is called by adding a side effect to the script
    script.install_called = False
    
    def mock_install():
        script.install_called = True
        
    script.at_install = mock_install
    
    obj.add_script(script)
    assert script.install_called is True

def test_script_db_serialization():
    # Use the Object-like create method the user added
    script = DummyBeforeScript.create(None, "TestScript", "Test Description")
    
    # In order for save_objects to save it, it must be in _ALL_OBJECTS and be is_modified
    obj_singleton.add_object(script)
    script.is_modified = True
    
    # Test getting save ops
    ops = script.get_save_ops()
    assert ops is not None
    
    # NOTE: get_save_ops() sets is_modified to False, but we want save_objects
    # to actually save it, so we must set it back to True for the test.
    script.is_modified = True
    
    # Save to the test database
    save_objects()
    
    # Clear memory to simulate a reboot
    _ALL_OBJECTS.clear()
    
    # Load from the database
    load_objects()
    
    # Assert it was loaded correctly
    assert script.id in _ALL_OBJECTS
    loaded_script = _ALL_OBJECTS[script.id]
    
    assert loaded_script.name == "TestScript"
    assert loaded_script.desc == "Test Description"
    assert getattr(loaded_script, "date_created", None) is not None

def test_node_add_remove_script():
    node = DummyNode(coord=("test_area", 0, 0, 0))
    script = DummyBeforeScript()
    script.id = 201

    node.add_script(script)
    assert script.id in node.scripts
    assert len(node.hooks.get("at_test_hook", set())) == 1

    node.remove_script(script)
    assert script.id not in node.scripts
    assert len(node.hooks.get("at_test_hook", set())) == 0

def test_node_hooks():
    node = DummyNode(coord=("test_area", 0, 0, 1))
    script = DummyBeforeScript()
    script.id = 202
    node.add_script(script)

    res = node.at_test_hook("n1", kwarg1="n2")
    assert node.log == ["before: n1, n2", "at_test_hook: n1, n2"]
    assert res == "original_result"

def test_attached_script_persistence():
    # Setup
    obj = DummyObj.create(None, "PersistObj")
    # Coordinates must be valid (area, x, y, z)
    coord = ("persist_area", 1, 1, 1)
    node = DummyNode(coord=coord)
    
    # Scripts
    obj_script = DummyBeforeScript.create(None, "ObjScript")
    node_script = DummyAfterScript.create(None, "NodeScript")

    obj.add_script(obj_script)
    node.add_script(node_script)

    # Initial test
    assert obj.at_test_hook("o1") == "original_result"
    assert node.at_test_hook("n1") == "after_result"

    # Save everything
    obj.is_modified = True
    obj_script.is_modified = True
    node_script.is_modified = True
    save_objects()
    
    nh = singletons_get.get_node_handler()
    nh.add_node(node)
    nh.save()

    # IDs for verification
    obj_id = obj.id
    obj_script_id = obj_script.id
    node_script_id = node_script.id

    # Clear memory
    _ALL_OBJECTS.clear()
    nh.clear()

    # Load everything
    load_objects()
    new_nh = singletons_get.get_node_handler()
    new_nh.load()
    
    # Verify Object script
    restored_obj = _ALL_OBJECTS[obj_id]
    restored_obj.log = [] # Reset log for clean test
    assert restored_obj.at_test_hook("o2") == "original_result"
    assert restored_obj.log == ["before: o2, None", "at_test_hook: o2, None"]

    # Verify Node script
    restored_node = new_nh.get_node(coord)
    assert restored_node is not None
    restored_node.log = []
    assert restored_node.at_test_hook("n2") == "after_result"
    assert restored_node.log == ["at_test_hook: n2, None", "after: n2, None"]
