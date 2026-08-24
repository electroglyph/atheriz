"""Issue tests: set/unset privilege escalation and attribute-protection.

These tests document CORRECT behavior; they fail until the corresponding
bugs (see issues.md) are fixed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.set import SetCommand, UnsetCommand
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def _make_caller(name="Alice", builder=True, msg=None):
    c = Object.create(None, name)
    c.privilege_level = (
        settings.Privilege.Builder if builder else settings.Privilege.Player
    )
    c.quelled = False
    c.msg = msg or MagicMock()
    return c


def _make_room(coord=None):
    if coord is None:
        coord = Coord("test", 0, 0, 0)
    r = Node(coord=coord, desc="A test room.", symbol="#")
    add_object(r)
    return r


class TestSetCommand:
    def test_cannot_escalate_privilege_via_set(self, global_test_env):
        """INTENT: `set` must not let a builder grant itself admin by setting
        the protected `privilege_level` attribute directly."""
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="privilege_level", value="5")
        SetCommand().run(c, args)
        assert c.privilege_level == settings.Privilege.Builder
        assert c.is_superuser is False

    def test_cannot_overwrite_lock_via_set(self, global_test_env):
        """INTENT: `set` must not replace the object's internal lock."""
        c = _make_caller(builder=True)
        orig_lock = c.lock
        args = MagicMock(target="me", attribute="lock", value="garbage")
        SetCommand().run(c, args)
        assert c.lock is orig_lock
        # object must remain fully functional
        assert c.name == "Alice"


class TestUnsetCommand:
    def test_unset_cannot_remove_lock(self, global_test_env):
        """INTENT: `unset` must not delete an object's lock; doing so would
        corrupt the object and crash the engine."""
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="lock")
        UnsetCommand().run(c, args)
        assert hasattr(c, "lock")
        assert c.name == "Alice"
