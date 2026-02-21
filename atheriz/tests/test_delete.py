import pytest
import tempfile
import shutil
import os
from unittest.mock import MagicMock

from atheriz import settings
from atheriz.database_setup import do_setup
from atheriz.singletons import get as singletons_get
from atheriz.singletons.objects import _ALL_OBJECTS, delete_objects, get as objects_get
from atheriz.singletons.get import get_node_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel



@pytest.fixture
def caller():
    c = Object.create(None, "Admin")
    c.privilege_level = 4 # superuser
    return c

@pytest.fixture
def room():
    r = Node(coord=("test", 0, 0, 0))
    handler = get_node_handler()
    handler.add_node(r)
    return r

def test_object_delete_non_recursive(caller, room):
    container = Object.create(caller, "Chest", is_container=True)
    container.move_to(room)
    item = Object.create(caller, "Gold")
    item.move_to(container)
    
    assert item in container.contents
    
    # Non-recursive delete: item should move to room (container's location)
    ops = container.delete(caller, recursive=False)
    assert ops is not None
    delete_objects(ops)
    
    assert container.is_deleted is True
    assert container.id not in _ALL_OBJECTS
    assert item.id in _ALL_OBJECTS
    assert item.location == room
    assert item in room.contents

def test_object_delete_recursive(caller, room):
    container = Object.create(caller, "Chest", is_container=True)
    container.move_to(room)
    item = Object.create(caller, "Gold")
    item.move_to(container)
    
    assert item in container.contents
    
    # Recursive delete: item should also be deleted
    ops = container.delete(caller, recursive=True)
    assert ops is not None
    delete_objects(ops)
    
    assert container.is_deleted is True
    assert container.id not in _ALL_OBJECTS
    assert item.is_deleted is True
    assert item.id not in _ALL_OBJECTS

def test_object_delete_lock(caller, room):
    item = Object.create(None, "Protected")
    item.move_to(room)
    
    # Add a lock that prevents deletion
    item.add_lock("delete", lambda x: False)
    
    # Deletion should be aborted (return None)
    ops = item.delete(caller)
    assert ops is None
    assert item.id in _ALL_OBJECTS
    assert item.is_deleted is False

def test_node_delete_non_recursive(caller, room):
    # Setup node and an item in it
    item = Object.create(caller, "Lamp")
    item.move_to(room)
    item.home = room # Normally home would be set to something else if we want to test move to home
    
    # Create another room to act as 'home'
    home_room = Node(coord=("test", 1, 1, 1))
    get_node_handler().add_node(home_room)
    item.home = home_room
    
    assert item in room.contents
    
    # Non-recursive node delete: item should move to its home
    result = room.delete(caller, recursive=False)
    assert result is not None
    _, ops = result
    delete_objects(ops)
    
    assert room.is_deleted is True
    assert get_node_handler().get_node(room.coord) is None
    assert item.location == home_room
    assert item in home_room.contents

def test_node_delete_recursive(caller, room):
    item = Object.create(caller, "Lamp")
    item.move_to(room)
    
    assert item in room.contents
    
    # Recursive node delete: item should be deleted
    result = room.delete(caller, recursive=True)
    assert result is not None
    _, ops = result
    delete_objects(ops)
    
    assert room.is_deleted is True
    assert item.is_deleted is True
    assert item.id not in _ALL_OBJECTS

def test_node_delete_registry(caller, room):
    coord = room.coord
    assert get_node_handler().get_node(coord) == room
    
    result = room.delete(caller)
    assert result is not None
    
    assert get_node_handler().get_node(coord) is None

def test_account_delete(caller):
    from atheriz.database_setup import get_database
    db = get_database()
    
    account = Account.create("TestAccount", "password")
    assert account is not None
    assert account.id in _ALL_OBJECTS
    
    # Save the account to DB first
    ops = account.get_save_ops()
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute(ops[0], ops[1])
        db.connection.commit()
    
    res = account.delete(caller, False)
    assert res is True
    assert account.is_deleted is True
    assert account.id not in _ALL_OBJECTS
    
    # Verify it is gone from DB
    with db.lock:
        cursor.execute("SELECT id FROM objects WHERE id = ?", (account.id,))
        assert cursor.fetchone() is None

def test_channel_delete(caller):
    from atheriz.database_setup import get_database
    db = get_database()
    
    channel = Channel.create("Public")
    assert channel is not None
    assert channel.id in _ALL_OBJECTS
    
    # Save the channel to DB first
    ops = channel.get_save_ops()
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute(ops[0], ops[1])
        db.connection.commit()
    
    res = channel.delete(caller, False)
    assert res is True
    assert channel.is_deleted is True
    assert channel.id not in _ALL_OBJECTS
    
    # Verify it is gone from DB
    with db.lock:
        cursor.execute("SELECT id FROM objects WHERE id = ?", (channel.id,))
        assert cursor.fetchone() is None

def test_delete_objects_utility():
    from atheriz.database_setup import get_database
    db = get_database()
    
    # Create an object and save it
    item = Object.create(None, "To-be-deleted")
    ops = item.get_save_ops()
    
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute(ops[0], ops[1])
        db.connection.commit()
    
    # Verify it exists in DB
    with db.lock:
        cursor.execute("SELECT id FROM objects WHERE id = ?", (item.id,))
        assert cursor.fetchone() is not None
    
    # Use delete_objects to remove it
    del_ops = [item.get_del_ops()]
    delete_objects(del_ops)
    
    # Verify it is gone from DB
    with db.lock:
        cursor.execute("SELECT id FROM objects WHERE id = ?", (item.id,))
        assert cursor.fetchone() is None
