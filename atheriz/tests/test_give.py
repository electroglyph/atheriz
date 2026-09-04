import pytest
from atheriz.utils import Coord
from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_obj import Object
from atheriz.globals import objects as obj_singleton
from atheriz.commands.loggedin.give import GiveCommand
from atheriz import settings
from pathlib import Path
import shutil
from unittest.mock import MagicMock
from atheriz.database_setup import get_database



def setup_give_scenario():
    # Setup Area, Grid, Node
    handler = NodeHandler()
    area = NodeArea(name="testarea")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("testarea", 0, 0, 0))
    grid.add_node(node)
    area.add_grid(grid)
    handler.add_area(area)

    # Setup Objects
    giver = Object.create(None, "giver", is_pc=True)
    giver.is_connected = True
    giver.location = node
    node.add_object(giver)

    receiver = Object.create(None, "receiver", is_pc=True)
    receiver.is_connected = True
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

def test_give_multiple_matches():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    # Second object named "receiver" in the room creates ambiguity.
    twin = Object.create(None, "receiver", is_pc=True)
    twin.is_connected = True
    twin.location = node
    node.add_object(twin)

    cmd = GiveCommand()
    args = cmd.parser.parse_args(["apple", "all", "receiver"])
    cmd.run(giver, args)

    giver.msg.assert_any_call("Multiple matches found for 'all receiver'.")
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


def test_give_to_self_fails():
    giver, receiver, node = setup_give_scenario()
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["apple", "giver"])
    cmd.run(giver, args)
    giver.msg.assert_called()
    assert "already have" in str(giver.msg.call_args_list).lower()
    assert item.location == giver


def test_give_to_offline_char_fails():
    giver, receiver, node = setup_give_scenario()
    receiver.is_connected = False
    item = Object.create(None, "apple", is_item=True)
    item.move_to(giver)
    cmd = GiveCommand()
    args = cmd.parser.parse_args(["apple", "receiver"])
    cmd.run(giver, args)
    giver.msg.assert_called()
    assert "could not find" in str(giver.msg.call_args_list).lower() or "offline" in str(giver.msg.call_args_list).lower()
    assert item.location == giver


class TestGiveRecipientConsent:
    def test_give_honors_recipient_give_lock(self, global_test_env):
        """SHOULD: the recipient's give lock is honored — a give lock on the
        target denying the giver refuses the transfer and the item stays with
        the giver (at_pre_give documents the lock as living on the receiving
        object, but the code checks the item's lock instead)."""
        giver, receiver, node = setup_give_scenario()
        receiver.add_lock("give", lambda accessor: False)
        assert receiver.access(giver, "give") is False
        item = Object.create(None, "apple", is_item=True)
        item.move_to(giver)

        cmd = GiveCommand()
        args = cmd.parser.parse_args(["apple", "receiver"])
        cmd.run(giver, args)

        assert item in giver.contents
        assert item.location == giver
        assert item not in receiver.contents
        sent = [c.args[0] for c in giver.msg.call_args_list if c.args]
        assert "You give apple to receiver." not in sent


class TestGiveBroadcastTemplate:
    def test_give_broadcast_uses_mapping_template(self, global_test_env):
        """SHOULD: the room broadcast goes through msg_contents mapping
        templates ($You/$obj) so per-recipient get_display_name applies,
        instead of f-string-baked names."""
        giver, receiver, node = setup_give_scenario()
        giver.name = "GivingGary"
        node.msg_contents = MagicMock()
        item = Object.create(None, "apple", is_item=True)
        item.move_to(giver)

        cmd = GiveCommand()
        args = cmd.parser.parse_args(["apple", "receiver"])
        cmd.run(giver, args)

        assert item.location == receiver
        node.msg_contents.assert_called_once()
        call = node.msg_contents.call_args
        template = call.args[0] if call.args else call.kwargs.get("text", "")
        assert giver.name not in template, f"baked giver name in broadcast template: {template!r}"
        assert receiver.name not in template, f"baked target name in broadcast template: {template!r}"
        assert item.name not in template, f"baked item name in broadcast template: {template!r}"
        mapping = call.kwargs.get("mapping", None)
        assert isinstance(mapping, dict), f"broadcast must pass mapping=..., got {call!r}"
        assert {"giver", "item", "target"} <= set(mapping)
