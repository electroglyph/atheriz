"""Issue tests: `move_to` never fires the Node enter/leave hooks for
node-to-node moves, and ignores the return value of `do_item_move`.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.base_script import replace
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def _make_nodes():
    n1 = Node(coord=Coord("test", 0, 0, 0))
    n2 = Node(coord=Coord("test", 0, 1, 0))
    add_object(n1)
    add_object(n2)
    return n1, n2


class TestNodeMoveHooks:
    def test_node_to_node_move_fires_enter_leave_hooks(self, global_test_env):
        """INTENT: moving an object between two nodes must invoke
        at_pre_object_leave / at_object_leave on the source node and
        at_pre_object_receive / at_object_receive on the destination node."""
        n1, n2 = _make_nodes()
        calls = []

        @replace
        def pre_leave(*args, **kwargs):
            calls.append("pre_leave")
            return True

        @replace
        def leave(*args, **kwargs):
            calls.append("leave")

        @replace
        def pre_receive(*args, **kwargs):
            calls.append("pre_receive")
            return True

        @replace
        def receive(*args, **kwargs):
            calls.append("receive")

        n1.hooks.setdefault("at_pre_object_leave", set()).add(pre_leave)
        n1.hooks.setdefault("at_object_leave", set()).add(leave)
        n2.hooks.setdefault("at_pre_object_receive", set()).add(pre_receive)
        n2.hooks.setdefault("at_object_receive", set()).add(receive)

        obj = Object.create(None, "wanderer", is_pc=True)
        obj.location = n1
        n1.add_object(obj)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = obj.move_to(n2, announce=False)

        assert ok is True
        assert calls == ["pre_leave", "leave", "pre_receive", "receive"]

    def test_pre_leave_false_aborts_node_move(self, global_test_env):
        """INTENT: if the source node's at_pre_object_leave returns False, the
        object must not leave."""
        n1, n2 = _make_nodes()

        @replace
        def pre_leave(*args, **kwargs):
            return False

        n1.hooks.setdefault("at_pre_object_leave", set()).add(pre_leave)

        obj = Object.create(None, "stuck", is_pc=True)
        obj.location = n1
        n1.add_object(obj)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = obj.move_to(n2, announce=False)

        assert ok is False
        assert obj.location == n1


class TestItemMoveReturn:
    def test_move_to_honors_container_move_refusal(self, global_test_env):
        """INTENT: when moving an item into a container and the source node's
        at_pre_object_leave refuses, move_to must return False (it currently
        discards do_item_move()'s return value and reports success)."""
        n1, n2 = _make_nodes()
        pack = Object.create(None, "pack", is_container=True)
        pack.location = n1
        n1.add_object(pack)

        item = Object.create(None, "ball", is_item=True)
        item.location = n1
        n1.add_object(item)

        @replace
        def pre_leave(*args, **kwargs):
            return False

        n1.hooks.setdefault("at_pre_object_leave", set()).add(pre_leave)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item.move_to(pack)

        assert ok is False
        assert item.location == n1
