import pytest
from unittest.mock import MagicMock
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.commands.loggedin.delete import DeleteCommand
from atheriz.singletons.objects import get, _ALL_OBJECTS
from atheriz.singletons.node import NodeHandler
from atheriz import settings, database_setup

import tempfile
import shutil
import os
from atheriz.database_setup import do_setup, get_database
from atheriz.singletons.get import get_node_handler

from atheriz.utils import strip_ansi

@pytest.fixture(autouse=True)
def temp_env():
    # Setup temp dir for database and saves
    old_save_path = settings.SAVE_PATH
    temp_dir = tempfile.mkdtemp()
    settings.SAVE_PATH = temp_dir
    
    # Initialize DB schema
    do_setup()
    
    # Clear singletons to ensure fresh state
    from atheriz.singletons import get
    get._NODE_HANDLER = None
    _ALL_OBJECTS.clear()
    
    yield
    
    # Cleanup: close DB before removing temp dir (Windows file locks)
    from atheriz.database_setup import _DATABASE
    import atheriz.database_setup as db_mod
    if db_mod._DATABASE is not None:
        db_mod._DATABASE.close()
    db_mod._DATABASE = None
    
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass  # Best-effort cleanup on Windows
    settings.SAVE_PATH = old_save_path
    get._NODE_HANDLER = None
    _ALL_OBJECTS.clear()

@pytest.fixture
def caller():
    c = Object.create(None, "Admin")
    c.privilege_level = 3 # builder
    c.msg = MagicMock()
    return c

@pytest.fixture
def room():
    r = Node(coord=("test", 0, 0, 0))
    # Node.name is read-only, r.name = "Test Room" would fail
    
    handler = get_node_handler()
    handler.add_node(r)
    return r

def test_delete_inventory_item(caller, room):
    caller.location = room
    item = Object.create(None, "Apple")
    item.move_to(caller)
    
    # Sanity check
    assert item in caller.contents
    assert item.id in _ALL_OBJECTS
    
    cmd = DeleteCommand()
    cmd.run(caller, cmd.parser.parse_args(["Apple"]))
    
    # Verify deletion
    assert item not in caller.contents
    assert item.id not in _ALL_OBJECTS
    assert item.is_deleted is True
    
    caller.msg.assert_called()
    args, _ = caller.msg.call_args
    assert "Deleted Apple" in strip_ansi(args[0])

def test_delete_room_item(caller, room):
    caller.location = room
    item = Object.create(None, "Sword")
    item.move_to(room)
    
    assert item in room.contents
    
    cmd = DeleteCommand()
    cmd.run(caller, cmd.parser.parse_args(["Sword"]))
    
    assert item not in room.contents
    assert item.id not in _ALL_OBJECTS
    assert "Deleted Sword" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_here(caller, room):
    caller.location = room
    
    cmd = DeleteCommand()
    cmd.run(caller, cmd.parser.parse_args(["here"]))
    
    assert room.is_deleted is True
    # Node name is str(coord)
    # count for node is result + 1. result is 0 (no items), so count = 1.
    assert "test,0,0,0" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_by_coord(caller, room):
    caller.location = room
    
    cmd = DeleteCommand()
    # Test (area,x,y,z) format
    cmd.run(caller, cmd.parser.parse_args(["(test,0,0,0)"]))
    
    assert room.is_deleted is True
    assert "test,0,0,0" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_recursive(caller, room):
    caller.location = room
    container = Object.create(None, "Chest", is_container=True)
    container.move_to(room)
    item = Object.create(None, "Gold")
    item.move_to(container)
    
    assert item in container.contents
    
    cmd = DeleteCommand()
    # Recursive delete
    cmd.run(caller, cmd.parser.parse_args(["Chest", "-r"]))
    
    assert container.id not in _ALL_OBJECTS
    assert item.id not in _ALL_OBJECTS
    assert "2 objects total" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_non_recursive(caller, room):
    caller.location = room
    container = Object.create(None, "Chest", is_container=True)
    container.move_to(room)
    item = Object.create(None, "Gold")
    item.move_to(container)
    
    cmd = DeleteCommand()
    cmd.run(caller, cmd.parser.parse_args(["Chest"]))
    
    assert container.id not in _ALL_OBJECTS
    assert item.id in _ALL_OBJECTS
    assert item.location == room # Moved to container's location
    assert item in room.contents
    assert "Deleted Chest" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_permission_denied(caller, room):
    caller.location = room
    # Lower privilege player cannot delete
    player = Object.create(None, "Player")
    player.privilege_level = 1
    player.msg = MagicMock()
    player.location = room
    
    item = Object.create(None, "Safe")
    item.move_to(room)
    
    # Command access check usually happens in cmdset, but we'll test both
    cmd = DeleteCommand()
    
    # 1. Test Command.access (usually handled by system)
    assert cmd.access(player) is False
    
    # 2. Test permission check inside run() for specific target
    # Builder privilege
    caller.privilege_level = 3
    # Explicit lock denying delete
    item.add_lock("delete", lambda x: False)
    
    cmd.run(caller, cmd.parser.parse_args(["Safe"]))
    assert item.id in _ALL_OBJECTS
    assert "do not have permission" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_no_match(caller, room):
    caller.location = room
    
    cmd = DeleteCommand()
    cmd.run(caller, cmd.parser.parse_args(["nothing"]))
    
    assert "No match found" in strip_ansi(caller.msg.call_args[0][0])

def test_delete_multiple_matches(caller, room):
    caller.location = room
    item1 = Object.create(None, "key")
    item1.move_to(room)
    item2 = Object.create(None, "key")
    item2.move_to(room)
    
    cmd = DeleteCommand()
    cmd.run(caller, cmd.parser.parse_args(["keys"]))
    
    assert "Multiple matches" in strip_ansi(caller.msg.call_args[0][0])
    assert item1.id in _ALL_OBJECTS
    assert item2.id in _ALL_OBJECTS

