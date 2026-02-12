import pytest
import argparse
from unittest.mock import MagicMock, patch
from atheriz.objects.base_obj import Object
from atheriz.singletons import objects
from atheriz.commands.loggedin.delete import DeleteCommand
from atheriz.objects.nodes import Node
from atheriz import settings

# Mock the Channel system to avoid errors during object creation/deletion
@pytest.fixture(autouse=True)
def mock_channels():
    with patch("atheriz.objects.base_obj.get_server_channel") as mock_get_channel:
        mock_channel = MagicMock()
        mock_get_channel.return_value = mock_channel
        yield mock_channel

@pytest.fixture(autouse=True)
def clear_registry():
    objects._ALL_OBJECTS.clear()
    objects.set_id(0)

class MockCaller(Object):
    def __init__(self):
        super().__init__()
        self.msgs = []
        self.privilege_level = 5  # Superuser, so is_builder is True
        self.location = None

    def msg(self, text=None, **kwargs):
        if text:
            self.msgs.append(text)
        super().msg(text, **kwargs)

    @property
    def is_builder(self):
        return True

def setup_test_env():
    # Create caller and location
    # We pretend location is a Node for search purposes, but it can be an Object for simplicity
    # or we can mock it.
    # The delete command expects caller.location to be a Node if searching in room.
    # But Object.search handles simple location contents too.
    
    # We'll use Objects for everything to separate from Node logic dependencies if possible.
    # But DeleteCommand type hints location as Node.
    
    room = Object.create(None, "Room", "A test room")
    caller = MockCaller()
    caller.name = "Caller"
    objects.add_object(caller)
    
    caller.move_to(room)
    
    return caller, room

def run_cmd(cmd_class, caller, args_str):
    cmd = cmd_class()
    # Mocking parser setup and parsing because Command.run expects parsed args usually
    # But DeleteCommand uses self.parser. It inherits from Command.
    # Command.parse() usually populates self.args.
    # However, DeleteCommand.run takes (caller, args) where args is the namespace.
    
    parser = argparse.ArgumentParser()
    cmd.parser = parser
    cmd.setup_parser()
    
    # Split args_str properly
    import shlex
    split_args = shlex.split(args_str)
    try:
        parsed_args = parser.parse_args(split_args)
    except SystemExit:
        raise Exception("Argument parser failed")
        
    cmd.run(caller, parsed_args)

def test_delete_basic():
    caller, room = setup_test_env()
    
    # Create item in room
    item = Object.create(None, "box", "A box")
    item.move_to(room)
    item_id = item.id
    
    assert objects.get(item_id) == [item]
    
    run_cmd(DeleteCommand, caller, "box")
    
    assert objects.get(item_id) == []
    assert item.location is None
    # Check "Deleted box." message
    assert any("Deleted box" in m for m in caller.msgs)

def test_delete_inventory():
    caller, room = setup_test_env()
    
    # Create item in inventory
    item = Object.create(None, "sword", "A sword")
    item.move_to(caller)
    item_id = item.id
    
    assert objects.get(item_id) == [item]
    
    run_cmd(DeleteCommand, caller, "sword")
    
    assert objects.get(item_id) == []
    assert any("Deleted sword" in m for m in caller.msgs)

def test_delete_recursive():
    caller, room = setup_test_env()
    
    # Create container with items
    container = Object.create(None, "chest", "A chest", is_container=True)
    assert container.move_to(room)
    
    inner = Object.create(None, "coin", "A coin", is_container=True) # Making it a container explicitly
    assert inner.move_to(container)
    
    inner_inner = Object.create(None, "gem", "A gem")
    assert inner_inner.move_to(inner) # Weird but possible in object model
    
    container_id = container.id
    inner_id = inner.id
    inner_inner_id = inner_inner.id
    
    # Ensure hierarchy is correct
    assert inner in container.contents
    assert inner_inner in inner.contents
    
    assert len(objects.get([container_id, inner_id, inner_inner_id])) == 3
    
    run_cmd(DeleteCommand, caller, "chest -r")
    
    remaining = objects.get([container_id, inner_id, inner_inner_id])
    assert remaining == [], f"Remaining objects: {remaining}"
    assert any("Deleted chest and 2 contained objects" in m for m in caller.msgs)

def test_delete_non_recursive_moves_contents():
    caller, room = setup_test_env()
    
    # Create container with items
    container = Object.create(None, "bag", "A bag", is_container=True)
    container.move_to(room)
    
    item = Object.create(None, "apple", "An apple")
    item.move_to(container)
    
    container_id = container.id
    item_id = item.id
    
    run_cmd(DeleteCommand, caller, "bag")
    
    # Container deleted
    assert objects.get(container_id) == []
    
    # Item preserved and moved to room
    item_ref = objects.get(item_id)
    assert len(item_ref) == 1
    assert item_ref[0].location == room
    
    assert any("Moved contents of bag to Room" in m for m in caller.msgs)
