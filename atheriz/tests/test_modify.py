import pytest
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import save_objects, load_objects, get
from atheriz import database_setup

def test_init_is_modified(global_test_env):
    """Test that Object() initializes with is_modified = True."""
    obj = Object()
    assert obj.is_modified is True

def test_create_is_modified(global_test_env):
    """Test that Object.create() results in an object with is_modified = True."""
    obj = Object.create(None, "Test Obj")
    assert obj.id is not None
    assert obj.is_modified is True

def test_save_resets_is_modified(global_test_env):
    """Test that save_objects() resets is_modified to False."""
    obj = Object.create(None, "Test Obj")
    assert obj.is_modified is True
    save_objects()
    assert obj.is_modified is False

def test_attribute_change_sets_is_modified(global_test_env):
    """Test that changing an attribute sets is_modified to True via the thread-safe patcher."""
    obj = Object.create(None, "Test Obj")
    save_objects()
    assert obj.is_modified is False
    
    # Changing name should trigger is_modified via ensure_thread_safe
    obj.name = "New Name"
    assert obj.is_modified is True
    
    save_objects()
    assert obj.is_modified is False
    
    # Changing desc should also trigger it
    obj.desc = "New Desc"
    assert obj.is_modified is True
    
    save_objects()
    assert obj.is_modified is False
    
    # Changing symbol should also trigger it
    obj.symbol = "Y"
    assert obj.is_modified is True

def test_save_optimization_logic(global_test_env):
    """Test that multiple objects track modification independently."""
    obj1 = Object.create(None, "Obj 1")
    obj2 = Object.create(None, "Obj 2")
    
    save_objects()
    assert obj1.is_modified is False
    assert obj2.is_modified is False
    
    # Modify only obj1
    obj1.name = "Modified 1"
    assert obj1.is_modified is True
    assert obj2.is_modified is False
    
    # After save, both should be False
    save_objects()
    assert obj1.is_modified is False
    assert obj2.is_modified is False

def test_load_is_modified_false(global_test_env):
    """Test that objects loaded from the database have is_modified = False."""
    obj = Object.create(None, "Persistent Obj")
    obj_id = obj.id
    save_objects()
    assert obj.is_modified is False
    
    # Force reload from DB
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    database_setup._CLOSED = False
    load_objects()
    
    loaded_obj = get(obj_id)[0]
    assert loaded_obj.name == "Persistent Obj"
    assert loaded_obj.is_modified is False

def test_move_is_modified(global_test_env):
    """Test that move_to() sets is_modified for the object and involved containers."""
    obj = Object.create(None, "Mobile Obj")
    container1 = Object.create(None, "Container 1", is_container=True)
    container2 = Object.create(None, "Container 2", is_container=True)
    
    save_objects()
    assert obj.is_modified is False
    assert container1.is_modified is False
    assert container2.is_modified is False
    
    # Initial move to container1
    obj.move_to(container1)
    assert obj.is_modified is True
    assert container1.is_modified is True
    
    save_objects()
    assert obj.is_modified is False
    assert container1.is_modified is False
    
    # Move from container1 to container2
    obj.move_to(container2)
    assert obj.is_modified is True
    assert container1.is_modified is True
    assert container2.is_modified is True
