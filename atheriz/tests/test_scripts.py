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




class DummyObj(Object):
    log: list = []

    def __init__(self):
        super().__init__()
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
