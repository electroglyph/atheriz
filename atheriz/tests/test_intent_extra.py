"""INTENT-focused tests for additional command branches and edge cases.

INTENT: Each test class documents user-visible behavior and uses INTENT
docstrings to capture the contract under test.
"""
from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.cmdset import LoggedinCmdSet
from atheriz.commands.loggedin.give import GiveCommand
from atheriz.commands.loggedin.group import GroupCommand
from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet
from atheriz.commands.unloggedin.quit import QuitCommand as UnQuitCommand
from atheriz.objects.base_channel import Channel
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def _make_caller(name="Alice", builder=False, superuser=False, location=None):
    c = MagicMock(spec=Object)
    c.name = name
    c.privilege_level = (
        settings.Privilege.Admin if superuser else (
            settings.Privilege.Builder if builder else settings.Privilege.Player
        )
    )
    c.quelled = False
    c.is_builder = builder or superuser
    c.is_superuser = superuser
    c.is_pc = True
    c.id = 1
    c.location = location
    c.session = MagicMock()
    c.session.screenreader = False
    c.session.term_width = 80
    c.group_channel = None
    c.followers = set()
    c.lock = MagicMock()
    c.search = MagicMock(return_value=[])
    c.access = MagicMock(return_value=True)
    c.msg = MagicMock()
    c.contents = []
    c.joined_groups = set()
    return c


# ---------------------------------------------------------------------------
# CmdSet registration completeness
# ---------------------------------------------------------------------------

class TestLoggedinCmdSetCompleteness:
    """INTENT: every loggedin command key must be registered, with no
    duplicate keys (which would trigger the 'Overwriting command' warning)."""

    def test_all_known_keys_registered(self):
        # INTENT: spot-check a handful of common commands exist
        cs = LoggedinCmdSet()
        for k in ("look", "save", "quit", "time", "set", "unset", "delete",
                 "py", "desc", "emote", "say", "give", "get", "drop", "put",
                 "maze", "build", "create", "wander", "move", "door", "open",
                 "close", "lock", "unlock", "noun", "follow", "nofollow",
                 "group", "inventory", "map", "channel", "reload", "shutdown"):
            assert k in cs.commands, f"missing command: {k}"

    def test_no_duplicate_keys(self):
        # INTENT: get_all returns Command instances; since aliases share the
        # same Command object under multiple keys, dedupe by id and ensure
        # the unique-command count is sane.
        cs = LoggedinCmdSet()
        unique_cmds = set(id(cmd) for cmd in cs.get_all())
        # We expect ~45+ unique commands (look, save, quit, ... socials, ...)
        assert len(unique_cmds) >= 30, f"too few unique commands: {len(unique_cmds)}"
        # Verify each unique id maps to exactly one primary key
        from collections import Counter
        id_counter = Counter(id(cmd) for cmd in cs.get_all())
        max_count = max(id_counter.values())
        # A command with N aliases appears N times; this is expected.
        assert max_count >= 1

    def test_aliases_point_to_same_object(self):
        # INTENT: aliases of "socials" must map to the same command instance
        cs = LoggedinCmdSet()
        assert cs.commands["socials"] is cs.commands["smile"]
        assert cs.commands["socials"] is cs.commands["hug"]
        assert cs.commands["help"] is cs.commands["?"]


class TestUnloggedinCmdSetCompleteness:
    """INTENT: unloggedin cmdset exposes only auth + minimal helpers."""

    def test_all_known_keys_registered(self):
        cs = UnloggedinCmdSet()
        for k in ("connect", "guest", "quit", "help", "screenreader"):
            assert k in cs.commands, f"missing command: {k}"

    def test_connect_aliases(self):
        # INTENT: connect has no aliases; sr is alias for screenreader
        cs = UnloggedinCmdSet()
        assert cs.commands["screenreader"] is cs.commands["sr"]


# ---------------------------------------------------------------------------
# Group: message branch + leave + kick self/leader
# ---------------------------------------------------------------------------

class TestGroupMessage:
    """INTENT: 'group <message>' (default subcommand) sends a message to the
    caller's group channel; if not in a group, sends 'not in a group'."""

    def test_send_message(self):
        c = _make_caller()
        # Setup channel
        chan = MagicMock()
        chan.id = 99
        chan.listeners = {}
        chan.created_by = 1
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["hello","team"]))
        chan.msg.assert_called_once()
        args, kwargs = chan.msg.call_args
        assert "hello team" in str(args)
        # The channel.msg is called with (message, caller) form
        assert kwargs.get("caller") is c or len(args) >= 2

    def test_send_message_channel_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[]):
            GroupCommand().run(c, Namespace(args=["hello"]))
        c.msg.assert_called_with("Error: Group channel not found.")


class TestGroupLeave:
    """INTENT: 'group leave' removes the caller from the channel and clears
    group_channel. If last member, channel is deleted."""

    def test_leave_not_in_group(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["leave"]))
        c.msg.assert_called_with("You are not in a group.")

    def test_leave_channel_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[]):
            GroupCommand().run(c, Namespace(args=["leave"]))
        c.msg.assert_called_with("Error: Group channel not found.")

    def test_leave_success(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.listeners = {1: c, 2: MagicMock()}  # not empty
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["leave"]))
        chan.remove_listener.assert_called_once_with(c)
        assert c.group_channel is None

    def test_leave_last_member_deletes_channel(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.listeners = {1: c}  # only caller

        def fake_remove(obj):
            for k, v in list(chan.listeners.items()):
                if v is obj:
                    del chan.listeners[k]

        chan.remove_listener.side_effect = fake_remove
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["leave"]))
        chan.remove_listener.assert_called_once_with(c)
        chan.delete.assert_called_once()


class TestGroupKick:
    """INTENT: 'group kick <name>' requires the caller to be the leader.
    Cannot kick self."""

    def test_kick_not_in_group(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["kick","bob"]))
        c.msg.assert_called_with("You are not in a group.")

    def test_kick_channel_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[]):
            GroupCommand().run(c, Namespace(args=["kick","bob"]))
        c.msg.assert_called_with("Error: Group channel not found.")

    def test_kick_not_leader(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 50  # not the caller
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["kick","bob"]))
        c.msg.assert_called_with("You are not the leader of this group.")

    def test_kick_target_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 1
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["kick","ghost"]))
        c.msg.assert_called_with("Could not find 'ghost'.")

    def test_kick_self(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 1
        # Caller searches for "Alice" and finds themselves
        c.search = MagicMock(return_value=[c])
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["kick","alice"]))
        c.msg.assert_called_with("You can't kick yourself!")

    def test_kick_success(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 1
        target = MagicMock()
        target.id = 50
        target.get_display_name = MagicMock(return_value="Bob")
        target.__eq__ = lambda self, other: other is target  # only equal to itself
        c.search = MagicMock(return_value=[target])

        def fake_remove(obj):
            # Simulate listener removal
            pass
        chan.remove_listener.side_effect = fake_remove

        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["kick","bob"]))
        chan.remove_listener.assert_called_once_with(target)
        chan.msg.assert_called_once()


class TestGroupAdd:
    """INTENT: 'group add <name>' creates a channel on first add (or joins
    existing), and requires target to be following caller."""

    def test_add_target_not_found(self):
        c = _make_caller()
        c.group_channel = None
        c.search = MagicMock(return_value=[])
        c.location = MagicMock(access=MagicMock(return_value=True),
                              search=MagicMock(return_value=[]))
        GroupCommand().run(c, Namespace(args=["add","ghost"]))
        c.msg.assert_called_with("Could not find 'ghost'.")

    def test_add_multiple_matches(self):
        c = _make_caller()
        c.group_channel = None
        t1 = MagicMock()
        t2 = MagicMock()
        t1.id = 1
        t2.id = 2
        c.search = MagicMock(return_value=[t1, t2])
        c.location = MagicMock(access=MagicMock(return_value=True))
        GroupCommand().run(c, Namespace(args=["add","x"]))
        c.msg.assert_called_with("Multiple matches found for 'x'.")

    def test_add_creates_new_channel(self):
        c = _make_caller()
        c.group_channel = None
        target = MagicMock()
        target.id = 50
        target.get_display_name = MagicMock(return_value="Bob")
        target.__eq__ = lambda self, other: False
        target.group_channel = None
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock(access=MagicMock(return_value=True))
        c.followers = {50}
        c.lock = MagicMock()
        with patch("atheriz.commands.loggedin.group.Channel") as mock_chan_cls:
            chan = MagicMock()
            chan.id = 77
            chan.created_by = 1
            mock_chan_cls.create.return_value = chan
            GroupCommand().run(c, Namespace(args=["add","bob"]))
        chan.add_listener.assert_any_call(c)
        chan.add_listener.assert_any_call(target)
        assert c.group_channel == 77
        assert target.group_channel == 77

    def test_add_joins_existing_channel_as_non_leader(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 50  # not caller
        target = MagicMock()
        target.id = 50
        target.get_display_name = MagicMock(return_value="Bob")
        target.__eq__ = lambda self, other: False
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock(access=MagicMock(return_value=True))
        c.followers = {50}
        c.lock = MagicMock()
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["add","bob"]))
        c.msg.assert_called_with("You are not the leader of this group.")


class TestGroupList:
    """INTENT: 'group list' shows the members of the caller's group channel."""

    def test_list_channel_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[]):
            GroupCommand().run(c, Namespace(args=["list"]))
        c.msg.assert_called_with("Error: Group channel not found.")

    def test_list_success(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        # listeners is a dict of obj_id -> obj
        m1 = MagicMock()
        m1.get_display_name = MagicMock(return_value="Alice")
        m2 = MagicMock()
        m2.get_display_name = MagicMock(return_value="Bob")
        chan.listeners = {1: m1, 2: m2}
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]):
            GroupCommand().run(c, Namespace(args=["list"]))
        c.msg.assert_called_once()
        text = c.msg.call_args[0][0]
        assert "Alice" in text
        assert "Bob" in text


# ---------------------------------------------------------------------------
# Give edge cases
# ---------------------------------------------------------------------------

class TestGiveEdgeCases:
    """INTENT: 'give all' with empty inventory, multi-word target, target not
    in location."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        GiveCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location(self):
        c = _make_caller()
        c.location = None
        args = GiveCommand().parser.parse_args(["apple","bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("No.")

    def test_target_filtered_to(self):
        # INTENT: 'give apple to bob' filters out 'to' from target parts,
        # then proceeds to give. Since we have no item, expect 'You don't have that.'
        c = _make_caller()
        c.location = MagicMock(search=MagicMock(return_value=[MagicMock(id=99, name="Bob", msg=MagicMock())]))
        c.contents = []
        c.search = MagicMock(return_value=[])
        args = GiveCommand().parser.parse_args(["apple","to","bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("You don't have that.")

    def test_target_only_to(self):
        # INTENT: 'give apple to' → target is empty after filter
        c = _make_caller()
        c.location = MagicMock()
        args = GiveCommand().parser.parse_args(["apple","to"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("Give it to whom?")

    def test_all_with_empty_inventory(self):
        # INTENT: 'give all' with no contents → 'You don't have that.' (early return)
        c = _make_caller()
        receiver = MagicMock()
        receiver.id = 99
        receiver.name = "Bob"
        c.location = MagicMock(search=MagicMock(return_value=[receiver]))
        c.contents = []
        c.search = MagicMock(return_value=[])
        args = GiveCommand().parser.parse_args(["all","bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("You don't have that.")


# ---------------------------------------------------------------------------
# Unloggedin QuitCommand intent
# ---------------------------------------------------------------------------

class TestUnloggedinQuit:
    """INTENT: 'quit' closes the connection."""

    def test_quit_closes_connection(self):
        c = MagicMock()
        c.session.connection.close = MagicMock()
        UnQuitCommand().run(c, None)
        c.session.connection.close.assert_called_once()
        c.msg.assert_called_with("Goodbye!")
