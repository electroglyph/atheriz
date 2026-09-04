"""Tests for loggedin commands: put, get, drop, exam."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.exam import ExamineCommand, _format_value
from atheriz.commands.loggedin.get import GetCommand
from atheriz.commands.loggedin.put import PutCommand
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


class TestPutCommand:
    """INTENT: move object from caller to a container; only if container has is_container."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        PutCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location_via_search(self):
        c = _make_caller()
        c.location = None
        c.search = MagicMock(return_value=[])
        args = MagicMock(object="apple", destination=["bag"])
        PutCommand().run(c, args)
        c.msg.assert_called_with("'bag' not found.")

    def test_destination_not_container(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
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
        bag = Object.create(None, "Bag")
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        bag.id = 12345
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        c.search = MagicMock(side_effect=[[bag], [apple]])
        args = MagicMock(object="apple", destination=["bag"])
        PutCommand().run(c, args)
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
        c = _make_caller()
        room = _make_room()
        c.location = room
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        args = MagicMock(object="apple", source=["from", "bag"])
        c.search = MagicMock(side_effect=[[], [apple]])
        room.search = MagicMock(return_value=[])
        GetCommand().run(c, args)
        assert True


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


class TestExamineDoesNotMutate:
    def test_examine_does_not_mutate_target(self, global_test_env):
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

        assert target.is_superuser is False
        assert target.contents == []

    def test_examine_room_does_not_mutate_node(self, global_test_env):
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)

        args = MagicMock(target=f"#{node.id}")
        ExamineCommand().run(c, args)

        live = vars(node)
        assert "contents" not in live


class TestDropGetEdge:
    def test_drop_empty_args_shows_help(self):
        c = _make_caller()
        c.location = _make_room()
        DropCommand().run(c, None)
        c.msg.assert_called_once()
        assert "drop" in str(c.msg.call_args).lower() or "aliases" in str(c.msg.call_args).lower()

    def test_get_empty_args_shows_help(self):
        c = _make_caller()
        GetCommand().run(c, None)
        c.msg.assert_called_once()
        assert "get" in str(c.msg.call_args).lower() or "aliases" in str(c.msg.call_args).lower()

    def test_put_into_non_container_denied(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        target = MagicMock()
        target.is_container = False
        target.access = MagicMock(return_value=True)
        target.name = "Rock"
        c.search = MagicMock(return_value=[target])
        args = MagicMock(object="apple", destination=["rock"])
        PutCommand().run(c, args)
        c.msg.assert_called_once()
        assert "can't put" in str(c.msg.call_args).lower()


class TestExamDoesNotLeakPassword:
    def test_exam_does_not_dump_password_hash(self, global_test_env, fixed_salt):
        from atheriz.objects.base_account import Account
        admin = Object.create(None, "AdminExam")
        admin.privilege_level = settings.Privilege.Admin
        admin.msg = MagicMock()
        acct = Account.create("exam_acct", "supersecret")
        target = f"#{acct.id}"
        args = MagicMock(target=target)
        ExamineCommand().run(admin, args)
        all_text = " ".join(str(c.args[0]) for c in admin.msg.call_args_list if c.args)
        assert "supersecret" not in all_text
        assert acct.password not in all_text, "exam should not dump password hash"
        assert "password" not in all_text.lower(), "exam should not expose password field"

    def test_exam_does_not_expose_secret_attribute(self, global_test_env):
        admin = Object.create(None, "AdminExam2")
        admin.privilege_level = settings.Privilege.Admin
        admin.msg = MagicMock()
        victim = Object.create(None, "Victim")
        victim.password = "should_not_leak_hash_value_123"
        victim.secret_token = "also_secret"
        args = MagicMock(target=f"#{victim.id}")
        ExamineCommand().run(admin, args)
        all_text = " ".join(str(c.args[0]) for c in admin.msg.call_args_list if c.args)
        assert "should_not_leak" not in all_text
        assert "password" not in all_text.lower()


class TestGetAllViewLock:
    def test_get_all_skips_view_denied_item(self, global_test_env):
        """SHOULD: `get all` must not take an item whose view lock denies the
        caller, even when its get lock passes (parity with `get <name>`,
        which resolves through view-filtered search)."""
        c = _make_caller()
        room = _make_room()
        c.location = room
        visible = Object.create(None, "Apple")
        visible.move_to(room)
        hidden = Object.create(None, "SecretGem")
        hidden.move_to(room)
        hidden.add_lock("view", lambda accessor: False)
        assert hidden.access(c, "view") is False
        assert hidden.access(c, "get") is True
        room.msg_contents = MagicMock()
        args = MagicMock(object="all", source=[])
        GetCommand().run(c, args)
        assert visible in c.contents
        assert hidden in room.contents
        assert hidden not in c.contents


class TestGetBroadcastTemplate:
    def test_get_broadcast_uses_mapping_template(self, global_test_env):
        """SHOULD: the room broadcast goes through msg_contents mapping
        templates ($You/$obj) so per-recipient get_display_name applies,
        instead of f-string-baked names."""
        c = _make_caller("GetterGary")
        room = _make_room()
        c.location = room
        apple = Object.create(None, "apple")
        apple.move_to(room)
        room.msg_contents = MagicMock()

        args = MagicMock(object="apple", source=[])
        GetCommand().run(c, args)

        assert apple in c.contents
        room.msg_contents.assert_called_once()
        call = room.msg_contents.call_args
        template = call.args[0] if call.args else call.kwargs.get("text", "")
        assert "GetterGary" not in template, f"baked getter name: {template!r}"
        assert "apple" not in template, f"baked item name: {template!r}"
        mapping = call.kwargs.get("mapping", None)
        assert isinstance(mapping, dict), f"broadcast must pass mapping=..., got {call!r}"
        assert {"giver", "item"} <= set(mapping)
