"""Tests for loggedin commands: set, unset — builder privilege and attribute protection."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.set import SetCommand, UnsetCommand
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def _make_caller(name="Alice", builder=False, msg=None):
    c = Object.create(None, name)
    c.privilege_level = settings.Privilege.Builder if builder else settings.Privilege.Player
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
    """INTENT: builder-only; set attribute on target via ast.literal_eval."""

    def test_access_requires_builder(self):
        c = _make_caller(builder=False)
        assert SetCommand().access(c) is False

    def test_access_allowed_for_builder(self):
        c = _make_caller(builder=True)
        assert SetCommand().access(c) is True

    def test_no_args_shows_help(self):
        c = _make_caller(builder=True)
        SetCommand().run(c, None)
        c.msg.assert_called_once()

    def test_target_me(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="my_attr", value="42")
        SetCommand().run(c, args)
        assert c.my_attr == 42

    def test_target_here(self):
        c = _make_caller(builder=True)
        room = _make_room()
        c.location = room
        args = MagicMock(target="here", attribute="my_attr", value="'hello'")
        SetCommand().run(c, args)
        assert room.my_attr == "hello"

    def test_target_by_id(self):
        c = _make_caller(builder=True)
        target = Object.create(None, "Target")
        target.id = 999
        add_object(target)
        args = MagicMock(target="#999", attribute="x", value="1")
        SetCommand().run(c, args)
        assert target.x == 1

    def test_target_by_id_invalid_format(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="#abc", attribute="x", value="1")
        SetCommand().run(c, args)
        c.msg.assert_called_with("Invalid ID format. Use #<number>.")

    def test_target_by_id_not_found(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="#99999", attribute="x", value="1")
        SetCommand().run(c, args)
        c.msg.assert_called_with("No object found with ID 99999.")

    def test_target_not_found(self):
        c = _make_caller(builder=True)
        c.search = MagicMock(return_value=[])
        args = MagicMock(target="missing", attribute="x", value="1")
        SetCommand().run(c, args)
        c.msg.assert_called_with("No match found for 'missing'.")

    def test_target_multiple_matches(self):
        c = _make_caller(builder=True)
        c.search = MagicMock(return_value=[Object.create(None, "A"), Object.create(None, "B")])
        args = MagicMock(target="x", attribute="y", value="1")
        SetCommand().run(c, args)
        assert any("Multiple matches" in str(call) for call in c.msg.call_args_list)

    def test_falls_back_to_plain_string(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="note", value="hello world")
        SetCommand().run(c, args)
        assert c.note == "hello world"

    def test_warns_for_new_attribute(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="brand_new", value="1")
        SetCommand().run(c, args)
        assert any("new attribute" in str(call) for call in c.msg.call_args_list)

    def test_cannot_escalate_privilege_via_set(self, global_test_env):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="privilege_level", value="5")
        SetCommand().run(c, args)
        assert c.privilege_level == settings.Privilege.Builder
        assert c.is_superuser is False

    def test_cannot_overwrite_lock_via_set(self, global_test_env):
        c = _make_caller(builder=True)
        orig_lock = c.lock
        args = MagicMock(target="me", attribute="lock", value="garbage")
        SetCommand().run(c, args)
        assert c.lock is orig_lock
        assert c.name == "Alice"


class TestUnsetCommand:
    def test_access_requires_builder(self):
        c = _make_caller(builder=False)
        assert UnsetCommand().access(c) is False

    def test_deletes_existing_attr(self):
        c = _make_caller(builder=True)
        c.foo = 1
        args = MagicMock(target="me", attribute="foo")
        UnsetCommand().run(c, args)
        assert not hasattr(c, "foo")

    def test_missing_attr_msg(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="nope")
        UnsetCommand().run(c, args)
        c.msg.assert_called_with("Alice has no attribute 'nope'.")

    def test_unset_cannot_remove_lock(self, global_test_env):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="lock")
        UnsetCommand().run(c, args)
        assert hasattr(c, "lock")
        assert c.name == "Alice"
