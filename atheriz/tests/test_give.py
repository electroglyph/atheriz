import pytest
from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.singletons.node import NodeHandler
from atheriz.objects.base_obj import Object
from atheriz.singletons import objects as obj_singleton
from atheriz.commands.loggedin.give import GiveCommand
from atheriz import settings
from pathlib import Path
import shutil
from unittest.mock import MagicMock
from atheriz.database_setup import get_database

TEST_SAVE_DIR = Path("test_give_data")

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup - redirect save path and clean up
    original_save_path = settings.SAVE_PATH
    settings.SAVE_PATH = str(TEST_SAVE_DIR)
    if TEST_SAVE_DIR.exists():
        try:
            shutil.rmtree(TEST_SAVE_DIR)
        except OSError:
            pass
    TEST_SAVE_DIR.mkdir(parents=True, exist_ok=True)

    obj_singleton._ALL_OBJECTS.clear()

    yield

    # Teardown
    get_database().close()
    settings.SAVE_PATH = original_save_path
    if TEST_SAVE_DIR.exists():
        try:
            shutil.rmtree(TEST_SAVE_DIR)
        except OSError:
            pass

def setup_give_scenario():
    # Setup Area, Grid, Node
    handler = NodeHandler()
    area = NodeArea(name="testarea")
    grid = NodeGrid(z=0)
    node = Node(coord=("testarea", 0, 0, 0))
    grid.add_node(node)
    area.add_grid(grid)
    handler.add_area(area)

    # Setup Objects
    giver = Object.create(None, "giver", is_pc=True)
    giver.location = node
    node.add_object(giver)

    receiver = Object.create(None, "receiver", is_pc=True)
    receiver.location = node
    node.add_object(receiver)

    # Mock msg to capture output
    giver.msg = MagicMock()
    receiver.msg = MagicMock()
    
    return giver, receiver, node

def test_give_item():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    
    cmd = GiveCommand()
    # Mocking call to shlex.split via Command.execute or just running it directly
    # 'give apple to receiver'
    args = cmd.parser.parse_args(["apple", "receiver"])
    cmd.run(giver, args)
    
    assert item.location == receiver
    assert item in receiver.contents
    assert item not in giver.contents
    
    # Verify messages
    giver.msg.assert_any_call("You give apple to receiver.")
    receiver.msg.assert_any_call("giver gives you apple.")

def test_give_all():
    giver, receiver, node = setup_give_scenario()
    item1 = Object.create(None, "apple", is_item=True)
    item2 = Object.create(None, "orange", is_item=True)
    item1.move_to(giver)
    item2.move_to(giver)
    
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["all", "receiver"])
    cmd.run(giver, args)
    
    assert item1.location == receiver
    assert item2.location == receiver
    assert item1 in receiver.contents
    assert item2 in receiver.contents
    assert not giver.contents

def test_give_multiple_same_name():
    giver, receiver, node = setup_give_scenario()
    sword1 = Object.create(None, "sword", is_item=True)
    sword2 = Object.create(None, "sword", is_item=True)
    sword1.move_to(giver)
    sword2.move_to(giver)
    
    cmd = GiveCommand()
    # 'give swords to receiver' - search for "swords" should return both
    args = cmd.parser.parse_args(["swords", "receiver"])
    cmd.run(giver, args)
    
    assert sword1.location == receiver
    assert sword2.location == receiver
    assert sword1 in receiver.contents
    assert sword2 in receiver.contents

def test_give_hooks():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "wand", is_item=True)
    item.move_to(giver)
    
    item.at_pre_give = MagicMock(return_value=True)
    item.at_give = MagicMock()
    
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["wand", "receiver"])
    cmd.run(giver, args)
    
    assert item.location == receiver
    item.at_pre_give.assert_called_with(giver, receiver)
    item.at_give.assert_called_with(giver, receiver)

def test_give_pre_give_blocked():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "ring", is_item=True)
    item.move_to(giver)
    
    # Block giving
    item.at_pre_give = MagicMock(return_value=False)
    
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["ring", "receiver"])
    cmd.run(giver, args)
    
    assert item.location == giver
    assert item in giver.contents
    item.at_pre_give.assert_called_with(giver, receiver)

def test_give_to_self():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["apple", "giver"])
    cmd.run(giver, args)
    
    assert item.location == giver
    giver.msg.assert_any_call("You already have that!")

def test_give_item_not_found():
    giver, receiver, node = setup_give_scenario()
    
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["sword", "receiver"])
    cmd.run(giver, args)
    
    giver.msg.assert_any_call("You don't have that.")

def test_give_target_not_found():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["apple", "nonexistent"])
    cmd.run(giver, args)
    
    giver.msg.assert_any_call("Could not find 'nonexistent' here.")
    assert item.location == giver

def test_give_with_to_preposition():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    
    cmd = GiveCommand()
    # 'give apple to receiver' -> args.object="apple", args.target=["to", "receiver"]
    args = cmd.parser.parse_args(["apple", "to", "receiver"])
    cmd.run(giver, args)
    
    assert item.location == receiver
    giver.msg.assert_any_call("You give apple to receiver.")
