"""Issue tests: give/get/drop/put broadcast a tuple to msg_contents and crash.

The commands pass `text=(f"...", {"type": ...})` (a tuple) to
`Node.msg_contents`, which funcparses the tuple and raises AttributeError
whenever a bystander is present to receive the message.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.drop import DropCommand
from atheriz.commands.loggedin.get import GetCommand
from atheriz.commands.loggedin.give import GiveCommand
from atheriz.commands.loggedin.put import PutCommand
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def _setup_room():
    node = Node(coord=Coord("test", 0, 0, 0))
    add_object(node)

    caller = Object.create(None, "caller", is_pc=True)
    caller.msg = MagicMock()
    caller.location = node
    node.add_object(caller)

    target = Object.create(None, "target", is_pc=True)
    target.msg = MagicMock()
    target.location = node
    node.add_object(target)

    # A bystander in the room forces the broadcast path to actually run.
    bystander = Object.create(None, "bystander", is_pc=True)
    bystander.msg = MagicMock()
    bystander.location = node
    node.add_object(bystander)

    return node, caller, target, bystander


class TestGiveCommand:
    def test_give_does_not_crash(self, global_test_env):
        """INTENT: `give` must not crash while broadcasting to the room."""
        node, caller, target, bystander = _setup_room()
        item = Object.create(None, "apple", is_item=True)
        item.move_to(caller)

        cmd = GiveCommand()
        args = cmd.parser.parse_args(["apple", "target"])
        cmd.run(caller, args)

        assert item.location == target
        assert item in target.contents


class TestGetCommand:
    def test_get_does_not_crash(self, global_test_env):
        """INTENT: `get` must not crash while broadcasting to the room."""
        node, caller, target, bystander = _setup_room()
        item = Object.create(None, "coin", is_item=True)
        item.move_to(node)

        cmd = GetCommand()
        args = cmd.parser.parse_args(["coin"])
        cmd.run(caller, args)

        assert item in caller.contents

    def test_cannot_get_from_another_player(self, global_test_env):
        """INTENT: `get <item> from <player>` must not loot another player's
        inventory."""
        node, caller, target, bystander = _setup_room()
        sword = Object.create(None, "sword", is_item=True)
        sword.move_to(target)

        cmd = GetCommand()
        args = cmd.parser.parse_args(["sword", "from", "target"])
        cmd.run(caller, args)

        assert sword.location == target
        assert sword not in caller.contents

    def test_builder_can_get_from_another_player(self, global_test_env):
        """INTENT: builders (and above) may take items from another player's
        inventory; only guests/normal players are blocked."""
        node, caller, target, bystander = _setup_room()
        caller.privilege_level = settings.Privilege.Builder
        sword = Object.create(None, "sword", is_item=True)
        sword.move_to(target)

        cmd = GetCommand()
        args = cmd.parser.parse_args(["sword", "from", "target"])
        cmd.run(caller, args)

        assert sword in caller.contents

    def test_builder_get_all_from_another_player(self, global_test_env):
        """INTENT: `get all from <player>` is also allowed for builders."""
        node, caller, target, bystander = _setup_room()
        caller.privilege_level = settings.Privilege.Builder
        sword = Object.create(None, "sword", is_item=True)
        sword.move_to(target)
        shield = Object.create(None, "shield", is_item=True)
        shield.move_to(target)

        cmd = GetCommand()
        args = cmd.parser.parse_args(["all", "from", "target"])
        cmd.run(caller, args)

        assert sword in caller.contents
        assert shield in caller.contents

    def test_cannot_get_all_from_another_player(self, global_test_env):
        """INTENT: `get all from <player>` must not loot a player's inventory
        for non-builders either."""
        node, caller, target, bystander = _setup_room()
        sword = Object.create(None, "sword", is_item=True)
        sword.move_to(target)

        cmd = GetCommand()
        args = cmd.parser.parse_args(["all", "from", "target"])
        cmd.run(caller, args)

        assert sword.location == target
        assert sword not in caller.contents


class TestDropCommand:
    def test_drop_does_not_crash(self, global_test_env):
        """INTENT: `drop` must not crash while broadcasting to the room."""
        node, caller, target, bystander = _setup_room()
        item = Object.create(None, "rock", is_item=True)
        item.move_to(caller)

        cmd = DropCommand()
        args = cmd.parser.parse_args(["rock"])
        cmd.run(caller, args)

        assert item.location == node
        assert item in node.contents


class TestPutCommand:
    def test_put_does_not_crash(self, global_test_env):
        """INTENT: `put` must not crash while broadcasting to the room."""
        node, caller, target, bystander = _setup_room()
        box = Object.create(None, "box", is_container=True)
        box.location = node
        node.add_object(box)
        item = Object.create(None, "gem", is_item=True)
        item.move_to(caller)

        cmd = PutCommand()
        args = cmd.parser.parse_args(["gem", "into", "box"])
        cmd.run(caller, args)

        assert item.location == box
        assert item in box.contents
