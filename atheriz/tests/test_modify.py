import pytest
import os
import shutil
import tempfile
from atheriz.objects.base_obj import Object
from atheriz.singletons.objects import save_objects, load_objects, get
from atheriz import settings, database_setup

@pytest.fixture
def db_setup():
    # Setup temp dir for database and saves
    old_save_path = settings.SAVE_PATH
    temp_dir = tempfile.mkdtemp()
    settings.SAVE_PATH = temp_dir
    
    # Re-initialize database singleton
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    else:
        database_setup._DATABASE = None
    database_setup.do_setup()
    
    # Reload objects (clears memory and loads from empty DB)
    from atheriz.singletons.objects import _ALL_OBJECTS
    _ALL_OBJECTS.clear()
    load_objects()
    
    yield
    
    # Teardown: Close connection and remove DB file
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass
    
    settings.SAVE_PATH = old_save_path
    _ALL_OBJECTS.clear()

def test_init_is_modified(db_setup):
    """Test that Object() initializes with is_modified = True."""
    obj = Object()
    assert obj.is_modified is True

def test_create_is_modified(db_setup):
    """Test that Object.create() results in an object with is_modified = True."""
    obj = Object.create(None, "Test Obj")
    assert obj.id is not None
    assert obj.is_modified is True

def test_save_resets_is_modified(db_setup):
    """Test that save_objects() resets is_modified to False."""
    obj = Object.create(None, "Test Obj")
    assert obj.is_modified is True
    save_objects()
    assert obj.is_modified is False

def test_attribute_change_sets_is_modified(db_setup):
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

def test_save_optimization_logic(db_setup):
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

def test_load_is_modified_false(db_setup):
    """Test that objects loaded from the database have is_modified = False."""
    obj = Object.create(None, "Persistent Obj")
    obj_id = obj.id
    save_objects()
    assert obj.is_modified is False
    
    # Force reload from DB
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    load_objects()
    
    loaded_obj = get(obj_id)[0]
    assert loaded_obj.name == "Persistent Obj"
    assert loaded_obj.is_modified is False

def test_move_is_modified(db_setup):
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
