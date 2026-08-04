"""Issue tests: `examine` writes property values into the target's live
instance dict (`vars(target)`), corrupting the object.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.exam import ExamineCommand
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object


class TestExamineCommand:
    def test_examine_does_not_mutate_target(self, global_test_env):
        """INTENT: examining an object must be read-only. Property values
        (contents, is_superuser, is_builder, ...) must not be written into the
        target's instance `__dict__`, which would shadow the class properties
        and corrupt the object."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        target = Object.create(None, "sword", is_item=True)
        target.privilege_level = settings.Privilege.Player
        add_object(target)

        args = MagicMock(target=f"#{target.id}")
        ExamineCommand().run(c, args)

        live = vars(target)
        assert "contents" not in live
        assert "is_superuser" not in live
        assert "is_builder" not in live
        assert "is_tickable" not in live

        # property behavior must be preserved, not shadowed
        assert target.is_superuser is False
        assert target.contents == []

    def test_examine_room_does_not_mutate_node(self, global_test_env):
        """INTENT: examining a node must not write properties into the node's
        instance dict either."""
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord

        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)

        args = MagicMock(target=f"#{node.id}")
        ExamineCommand().run(c, args)

        live = vars(node)
        assert "contents" not in live
