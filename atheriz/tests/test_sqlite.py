
import pytest
import os
import sqlite3
from atheriz.objects.base_obj import Object
from atheriz.singletons.objects import save_objects, load_objects, delete_objects, get
from atheriz import settings, database_setup
import dill

@pytest.fixture
def db_setup():
    # Setup: Ensure DB directory exists and clean up previous DB
    if not os.path.exists(settings.SAVE_PATH):
        os.makedirs(settings.SAVE_PATH)
    
    db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
    if os.path.exists(db_path):
        os.remove(db_path)
        
    # Re-initialize database singleton
    database_setup._DATABASE = None
    database_setup.do_setup()
    
    # Reload objects (clears memory and loads from empty DB)
    load_objects()
    
    yield
    
    # Teardown: Close connection and remove DB file
    if database_setup._DATABASE:
        database_setup._DATABASE.connection.close()
        database_setup._DATABASE = None
    
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def superuser():
    # Create a superuser for performing deletions
    su = Object.create(None, "Superuser")
    su.privilege_level = 5 # Ensure superuser status
    return su

def test_save_load_object(db_setup):
    # Create an object
    obj = Object.create(None, "Test Object", "A test object")
    obj_id = obj.id
    obj.is_modified = True # Ensure it gets saved
    
    # Save objects to DB
    save_objects()
    
    # Clear memory
    database_setup._DATABASE.connection.close()
    database_setup._DATABASE = None
    
    # Load objects from DB
    load_objects()
    
    loaded_obj = get(obj_id)
    assert len(loaded_obj) == 1
    assert loaded_obj[0].name == "Test Object"
    assert loaded_obj[0].desc == "A test object"

def test_delete_object(db_setup, superuser):
    # Create an object
    obj = Object.create(None, "Object to Delete")
    obj_id = obj.id
    obj.is_modified = True
    save_objects()
    
    # Ensure it's in DB
    db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM objects WHERE id=?", (obj_id,))
    assert cursor.fetchone()[0] == 1
    conn.close()
    
    # Delete object
    # delete() returns ops, and we must call delete_objects() to execute them
    ops = obj.delete(superuser) 
    assert ops is not None
    assert len(ops) > 0
    
    # Verify object is removed from memory
    assert len(get(obj_id)) == 0
    
    # Execute deletion in DB
    delete_objects(ops)
    
    # Verify object is removed from DB
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM objects WHERE id=?", (obj_id,))
    assert cursor.fetchone()[0] == 0
    conn.close()

def test_recursive_delete(db_setup, superuser):
    # Create container and item
    container = Object.create(None, "Container", is_container=True)
    item = Object.create(None, "Item", is_item=True)
    item.move_to(container)
    
    container_id = container.id
    item_id = item.id
    
    container.is_modified = True
    item.is_modified = True
    save_objects()
    
    # Delete container recursively
    ops = container.delete(superuser, recursive=True)
    assert ops is not None
    
    # Only the recursive delete should generate multiple ops if it was correctly implemented to return all ops
    # The current implementation collects ops from all deleted objects
    assert len(ops) >= 2 # At least container and item
    
    delete_objects(ops)
    
    # Verify both are gone from DB
    db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM objects WHERE id=?", (container_id,))
    assert cursor.fetchone()[0] == 0
    
    cursor.execute("SELECT count(*) FROM objects WHERE id=?", (item_id,))
    assert cursor.fetchone()[0] == 0
    conn.close()

def test_map_handler_persistence(db_setup):
    from atheriz.singletons.map import MapHandler, MapInfo
    
    # Initialize handler (loads from empty DB)
    mh = MapHandler()
    assert len(mh.data) == 0
    
    # Add data
    mi = MapInfo(name="TestArea")
    mh.set_mapinfo("TestArea", 0, mi)
    
    # Save
    mh.save()
    
    # Verify DB content
    db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM mapdata WHERE area=? AND z=?", ("TestArea", 0))
    assert cursor.fetchone()[0] == 1
    conn.close()
    
    # Reload handler
    mh2 = MapHandler()
    assert ("TestArea", 0) in mh2.data
    assert mh2.data[("TestArea", 0)].name == "TestArea"

def test_node_handler_persistence(db_setup):
    from atheriz.singletons.node import NodeHandler
    from atheriz.objects.nodes import NodeArea, NodeGrid, NodeLink, Transition, Door
    
    # Initialize handler
    nh = NodeHandler()
    
    # Create Area
    area = NodeArea("TestArea")
    nh.add_area(area)
    
    # Create Transition
    # Transition signature: from_coord, to_coord
    t = Transition(("OtherArea", 0, 0, 0), ("TestArea", 1, 1, 0))
    nh.add_transition(t)
    
    # Create Door
    door = Door(("TestArea", 5, 5, 0), "exit", ("TestArea", 6, 5, 0), "entrance")
    nh.add_door(door)
    
    # Save
    nh.save()
    
    # Verify DB content
    db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM areas WHERE name=?", ("TestArea",))
    assert cursor.fetchone()[0] == 1
    
    cursor.execute("SELECT count(*) FROM transitions WHERE to_area=?", ("TestArea",))
    assert cursor.fetchone()[0] == 1
    
    # Fix for door check: doors in DB are stored by coordinate blocks
    # One row per coordinate that has doors
    cursor.execute("SELECT count(*) FROM doors WHERE area=? AND x=? AND y=? AND z=?", ("TestArea", 5, 5, 0))
    assert cursor.fetchone()[0] == 1
    
    conn.close()
    
    # Reload handler
    nh2 = NodeHandler()
    
    assert "TestArea" in nh2.areas
    assert ("TestArea", 1, 1, 0) in nh2.transitions
    assert ("TestArea", 5, 5, 0) in nh2.doors
    assert "exit" in nh2.doors[("TestArea", 5, 5, 0)]
