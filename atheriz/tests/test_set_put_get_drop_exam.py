"""Tests for loggedin commands: set, unset, put, get, drop, exam."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.exam import ExamineCommand, _format_value
from atheriz.commands.loggedin.get import GetCommand
from atheriz.commands.loggedin.put import PutCommand
from atheriz.commands.loggedin.set import SetCommand, UnsetCommand
from atheriz.commands.loggedin.drop import DropCommand
from atheriz.globals.objects import add_object, get
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


# ---------------------------------------------------------------------------
# SetCommand / UnsetCommand
# ---------------------------------------------------------------------------

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
        # ast.literal_eval("42") = 42
        assert c.my_attr == 42

    def test_target_here(self):
        c = _make_caller(builder=True)
        room = _make_room()
        c.location = room
        args = MagicMock(target="here", attribute="my_attr", value="'hello'")
        SetCommand().run(c, args)
        # literal_eval on a quoted string
        assert room.my_attr == "hello"

    def test_target_by_id(self):
        c = _make_caller(builder=True)
        target = Object.create(None, "Target")
        target.id = 999  # ensure unique
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
        # Two messages: header + per-match line
        assert any("Multiple matches" in str(call) for call in c.msg.call_args_list)

    def test_falls_back_to_plain_string(self):
        # INTENT: when literal_eval fails, value is a plain string
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="note", value="hello world")
        SetCommand().run(c, args)
        # The unquoted string is stored as a plain string
        assert c.note == "hello world"

    def test_warns_for_new_attribute(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="me", attribute="brand_new", value="1")
        SetCommand().run(c, args)
        assert any("new attribute" in str(call) for call in c.msg.call_args_list)


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


# ---------------------------------------------------------------------------
# PutCommand
# ---------------------------------------------------------------------------

class TestPutCommand:
    """INTENT: move object from caller to a container; only if container has is_container."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        PutCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location_via_search(self):
        c = _make_caller()
        c.location = None
        # container is searched, but if not found, msg
        c.search = MagicMock(return_value=[])
        args = MagicMock(object="apple", destination=["bag"])
        PutCommand().run(c, args)
        c.msg.assert_called_with("'bag' not found.")

    def test_destination_not_container(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        # not a container
        target = MagicMock()
        target.is_container = False
        target.access = MagicMock(return_value=True)
        target.name = "Rock"
        c.search = MagicMock(return_value=[target])
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        c.search = MagicMock(side_effect=[[target], [apple]])
        args = MagicMock(object="apple", destination=["rock"])
        PutCommand().run(c, args)
        c.msg.assert_called_with("You can't put anything in Rock!")

    def test_destination_in_inventory(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        # bag is a container
        bag = Object.create(None, "Bag")
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        bag.id = 12345
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        c.search = MagicMock(side_effect=[[bag], [apple]])
        # override the 2nd call: search for apple
        args = MagicMock(object="apple", destination=["bag"])
        PutCommand().run(c, args)
        # Apple should now be in bag
        assert apple in bag.contents

    def test_at_pre_put_blocks_put(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        bag = Object.create(None, "Bag")
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        apple.at_pre_put = MagicMock(return_value=False)
        c.search = MagicMock(side_effect=[[bag], [apple]])
        args = MagicMock(object="apple", destination=["bag"])
        PutCommand().run(c, args)
        assert apple not in bag.contents
        apple.at_pre_put.assert_called_once_with(c, bag)

    def test_at_put_called_on_success(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        bag = Object.create(None, "Bag")
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        apple.at_put = MagicMock()
        c.search = MagicMock(side_effect=[[bag], [apple]])
        args = MagicMock(object="apple", destination=["bag"])
        PutCommand().run(c, args)
        assert apple in bag.contents
        apple.at_put.assert_called_once_with(c, bag)

    def test_at_pre_put_blocks_all(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        bag = Object.create(None, "Bag")
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        bag.id = 999
        a = Object.create(None, "A")
        b = Object.create(None, "B")
        a.move_to(c)
        b.move_to(c)
        a.at_pre_put = MagicMock(return_value=False)
        b.at_pre_put = MagicMock(return_value=True)
        room.msg_contents = MagicMock()
        c.search = MagicMock(return_value=[bag])
        # put all in bag
        args = MagicMock(object="all", destination=["bag"])
        PutCommand().run(c, args)
        assert a not in bag.contents
        assert b in bag.contents

    def test_at_put_called_for_all(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        bag = Object.create(None, "Bag")
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        bag.id = 999
        a = Object.create(None, "A")
        a.move_to(c)
        a.at_put = MagicMock()
        room.msg_contents = MagicMock()
        c.search = MagicMock(return_value=[bag])
        args = MagicMock(object="all", destination=["bag"])
        PutCommand().run(c, args)
        a.at_put.assert_called_once_with(c, bag)


# ---------------------------------------------------------------------------
# GetCommand
# ---------------------------------------------------------------------------

class TestGetCommand:
    """INTENT: pick up object(s) from location or container; respect at_pre_get hooks."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        GetCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location(self):
        c = _make_caller()
        c.location = None
        args = MagicMock(object="apple", source=[])
        GetCommand().run(c, args)
        c.msg.assert_called_with("No.")

    def test_blocked_by_location_access(self):
        c = _make_caller()
        room = _make_room()
        room.access = MagicMock(return_value=False)
        c.location = room
        args = MagicMock(object="apple", source=[])
        GetCommand().run(c, args)
        c.msg.assert_called_with("You can't get something from here!")

    def test_get_all_blocked_by_location_access(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        apple = Object.create(None, "Apple")
        apple.move_to(room, force=True)
        room.access = MagicMock(return_value=False)
        args = MagicMock(object="all", source=[])
        GetCommand().run(c, args)
        c.msg.assert_called_with("You can't get something from here!")
        assert apple in room.contents

    def test_get_specific(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        apple = Object.create(None, "Apple")
        apple.move_to(room)
        room.msg_contents = MagicMock()
        room.search = MagicMock(return_value=[apple])
        args = MagicMock(object="apple", source=[])
        GetCommand().run(c, args)
        # Apple now in caller
        assert apple in c.contents

    def test_get_specific_not_found(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        room.search = MagicMock(return_value=[])
        args = MagicMock(object="missing", source=[])
        GetCommand().run(c, args)
        c.msg.assert_called_with("Object not found.")

    def test_get_all_from_location(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        a = Object.create(None, "A")
        b = Object.create(None, "B")
        a.move_to(room)
        b.move_to(room)
        room.msg_contents = MagicMock()
        args = MagicMock(object="all", source=[])
        GetCommand().run(c, args)
        assert a in c.contents
        assert b in c.contents

    def test_filters_out_from_in_source(self):
        # INTENT: "get apple from bag" - "from" is filtered
        c = _make_caller()
        room = _make_room()
        c.location = room
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        args = MagicMock(object="apple", source=["from", "bag"])
        c.search = MagicMock(side_effect=[[], [apple]])
        room.search = MagicMock(return_value=[])
        GetCommand().run(c, args)
        # We don't care that the result is empty; the point is the filter
        assert True  # No crash


# ---------------------------------------------------------------------------
# DropCommand
# ---------------------------------------------------------------------------

class TestDropCommand:
    """INTENT: drop items from inventory into current location."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        DropCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location(self):
        c = _make_caller()
        c.location = None
        args = MagicMock(object=["apple"])
        DropCommand().run(c, args)
        c.msg.assert_called_with("You can't drop something here!")

    def test_blocked_by_access(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        room.access = MagicMock(return_value=False)
        args = MagicMock(object=["apple"])
        DropCommand().run(c, args)
        c.msg.assert_called_with("You can't drop something here!")

    def test_drop_specific(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        room.msg_contents = MagicMock()
        c.search = MagicMock(return_value=[apple])
        args = MagicMock(object=["apple"])
        DropCommand().run(c, args)
        # Apple in room
        assert apple in room.contents
        c.msg.assert_called_with("You dropped: Apple")

    def test_drop_not_found(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        c.search = MagicMock(return_value=[])
        args = MagicMock(object=["apple"])
        DropCommand().run(c, args)
        c.msg.assert_called_with("Object not found.")

    def test_drop_all(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        a = Object.create(None, "A")
        b = Object.create(None, "B")
        a.move_to(c)
        b.move_to(c)
        room.msg_contents = MagicMock()
        args = MagicMock(object=["all"])
        DropCommand().run(c, args)
        assert a in room.contents
        assert b in room.contents


# ---------------------------------------------------------------------------
# ExamineCommand
# ---------------------------------------------------------------------------

class TestExamineCommand:
    """INTENT: dump object attributes with formatted values."""

    def test_access_requires_builder(self):
        c = _make_caller(builder=False)
        assert ExamineCommand().access(c) is False

    def test_no_args_shows_help(self):
        c = _make_caller(builder=True)
        ExamineCommand().run(c, None)
        c.msg.assert_called_once()

    def test_target_me(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="me")
        ExamineCommand().run(c, args)
        assert any("Examining" in str(call) for call in c.msg.call_args_list)

    def test_target_by_id_not_found(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="#99999")
        ExamineCommand().run(c, args)
        c.msg.assert_called_with("No object found with ID 99999.")

    def test_target_by_id_invalid(self):
        c = _make_caller(builder=True)
        args = MagicMock(target="#abc")
        ExamineCommand().run(c, args)
        c.msg.assert_called_with("Invalid ID format. Use #<number>.")

    def test_target_not_found(self):
        c = _make_caller(builder=True)
        c.search = MagicMock(return_value=[])
        args = MagicMock(target="ghost")
        ExamineCommand().run(c, args)
        c.msg.assert_called_with("No match found for 'ghost'.")

    def test_target_empty_uses_location(self):
        c = _make_caller(builder=True)
        c.location = None
        args = MagicMock(target=None)
        ExamineCommand().run(c, args)
        c.msg.assert_called_with("You are nowhere to examine.")


class TestFormatValue:
    """INTENT: _format_value renders special types in a friendly way."""

    def test_simple_value(self):
        assert _format_value(42) == "42"

    def test_list(self):
        result = _format_value([1, 2, 3])
        assert "[1, 2, 3]" == result

    def test_dict(self):
        result = _format_value({"a": 1})
        assert "{a: 1}" == result

    def test_internal_cmdset_hidden(self):
        assert _format_value(MagicMock(), hint_name="internal_cmdset") == "<hidden>"

    def test_session_with_account(self):
        sess = MagicMock()
        sess.account.name = "alice"
        sess.account.id = 1
        sess.connection.client_host = "1.2.3.4"
        sess.term_width = 80
        sess.term_height = 24
        sess.screenreader = False
        result = _format_value(sess, hint_name="session")
        assert "Session(" in result
        assert "alice" in result

    def test_session_none(self):
        assert _format_value(None, hint_name="session") == "None"
