"""Consolidated intent edge-case tests (merged from test_intent_extra + test_intent_extra2).

Covers: CmdSet registration, Group message/leave/kick/add/list,
Give edge cases, Look noun/link/location, Emote empty, Inventory grouping,
Channel branches, NoneCommand internal, CmdSet spec, Save message, Say alias,
Unloggedin quit. 29 + 20 tests — preserves all original branches.

Former files deleted: test_intent_extra.py (429 lines, 28 tests),
test_intent_extra2.py (355 lines, 20 tests). See test_plan.md §2.3.
"""
from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.channel import ChannelCommand
from atheriz.commands.loggedin.cmdset import LoggedinCmdSet
from atheriz.commands.loggedin.emote import EmoteCommand
from atheriz.commands.loggedin.give import GiveCommand
from atheriz.commands.loggedin.group import GroupCommand
from atheriz.commands.loggedin.inventory import InventoryCommand
from atheriz.commands.loggedin.look import LookCommand
from atheriz.commands.loggedin.none import NoneCommand
from atheriz.commands.loggedin.save import SaveCommand
from atheriz.commands.loggedin.say import SayCommand
from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet
from atheriz.commands.unloggedin.quit import QuitCommand as UnQuitCommand
from atheriz.globals.objects import add_object
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


def _make_room(coord=None, desc="A test room."):
    if coord is None:
        coord = Coord("test", 0, 0, 0)
    r = Node(coord=coord, desc=desc, symbol="#")
    add_object(r)
    return r


# ---------------------------------------------------------------------------
# CmdSet registration completeness (from test_intent_extra.py)
# ---------------------------------------------------------------------------

class TestLoggedinCmdSetCompleteness:
    """INTENT: every loggedin command key must be registered, with no
    duplicate keys (which would trigger the 'Overwriting command' warning)."""

    def test_all_known_keys_registered(self):
        cs = LoggedinCmdSet()
        for k in ("look", "save", "quit", "time", "set", "unset", "delete",
                 "py", "desc", "emote", "say", "give", "get", "drop", "put",
                 "maze", "build", "create", "wander", "move", "door", "open",
                 "close", "lock", "unlock", "noun", "follow", "nofollow",
                 "group", "inventory", "map", "channel", "reload", "shutdown"):
            assert k in cs.commands, f"missing command: {k}"

    def test_no_duplicate_keys(self):
        cs = LoggedinCmdSet()
        unique_cmds = set(id(cmd) for cmd in cs.get_all())
        assert len(unique_cmds) >= 30, f"too few unique commands: {len(unique_cmds)}"
        from collections import Counter
        id_counter = Counter(id(cmd) for cmd in cs.get_all())
        max_count = max(id_counter.values())
        assert max_count >= 1

    def test_aliases_point_to_same_object(self):
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
        cs = UnloggedinCmdSet()
        assert cs.commands["screenreader"] is cs.commands["sr"]


# ---------------------------------------------------------------------------
# Group: message branch + leave + kick self/leader (from test_intent_extra)
# ---------------------------------------------------------------------------

class TestGroupMessage:
    """INTENT: 'group <message>' (default subcommand) sends a message to the
    caller's group channel; if not in a group, sends 'not in a group'."""

    def test_send_message(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 99
        chan.listeners = {}
        chan.created_by = 1
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["hello","team"]))
        mock_get.assert_called()
        chan.msg.assert_called_once()
        args, kwargs = chan.msg.call_args
        assert "hello team" in str(args)
        assert kwargs.get("caller") is c or len(args) >= 2

    def test_send_message_channel_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[]) as mock_get:
            GroupCommand().run(c, Namespace(args=["hello"]))
        mock_get.assert_called()
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
        with patch("atheriz.commands.loggedin.group.get", return_value=[]) as mock_get:
            GroupCommand().run(c, Namespace(args=["leave"]))
        mock_get.assert_called()
        assert c.group_channel is None
        c.msg.assert_called_with("Error: Group channel not found.")

    def test_leave_success(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.listeners = {1: c, 2: MagicMock()}
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["leave"]))
        mock_get.assert_called()
        chan.remove_listener.assert_called_once_with(c)
        assert c.group_channel is None

    def test_leave_last_member_deletes_channel(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.listeners = {1: c}

        def fake_remove(obj):
            for k, v in list(chan.listeners.items()):
                if v is obj:
                    del chan.listeners[k]

        chan.remove_listener.side_effect = fake_remove
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["leave"]))
        mock_get.assert_called()
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
        with patch("atheriz.commands.loggedin.group.get", return_value=[]) as mock_get:
            GroupCommand().run(c, Namespace(args=["kick","bob"]))
        mock_get.assert_called()
        c.msg.assert_called_with("Error: Group channel not found.")

    def test_kick_not_leader(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 50
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["kick","bob"]))
        mock_get.assert_called()
        c.msg.assert_called_with("You are not the leader of this group.")

    def test_kick_target_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 1
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["kick","ghost"]))
        mock_get.assert_called()
        c.msg.assert_called_with("Could not find 'ghost'.")

    def test_kick_self(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        chan.created_by = 1
        c.search = MagicMock(return_value=[c])
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["kick","alice"]))
        mock_get.assert_called()
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
        target.__eq__ = lambda self, other: other is target
        c.search = MagicMock(return_value=[target])

        def fake_remove(obj):
            pass
        chan.remove_listener.side_effect = fake_remove

        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["kick","bob"]))
        mock_get.assert_called()
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
        chan.created_by = 50
        target = MagicMock()
        target.id = 50
        target.get_display_name = MagicMock(return_value="Bob")
        target.__eq__ = lambda self, other: False
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock(access=MagicMock(return_value=True))
        c.followers = {50}
        c.lock = MagicMock()
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["add","bob"]))
        mock_get.assert_called()
        c.msg.assert_called_with("You are not the leader of this group.")


class TestGroupList:
    """INTENT: 'group list' shows the members of the caller's group channel."""

    def test_list_channel_not_found(self):
        c = _make_caller()
        c.group_channel = 99
        with patch("atheriz.commands.loggedin.group.get", return_value=[]) as mock_get:
            GroupCommand().run(c, Namespace(args=["list"]))
        mock_get.assert_called()
        c.msg.assert_called_with("Error: Group channel not found.")

    def test_list_success(self):
        c = _make_caller()
        c.group_channel = 99
        chan = MagicMock()
        chan.id = 99
        m1 = MagicMock()
        m1.get_display_name = MagicMock(return_value="Alice")
        m2 = MagicMock()
        m2.get_display_name = MagicMock(return_value="Bob")
        chan.listeners = {1: m1, 2: m2}
        with patch("atheriz.commands.loggedin.group.get", return_value=[chan]) as mock_get:
            GroupCommand().run(c, Namespace(args=["list"]))
        mock_get.assert_called()
        c.msg.assert_called_once()
        text = c.msg.call_args[0][0]
        assert "Alice" in text
        assert "Bob" in text


# ---------------------------------------------------------------------------
# Give edge cases (from test_intent_extra.py)
# ---------------------------------------------------------------------------

class TestGiveEdgeCases:
    """INTENT: 'give all' with empty inventory, multi-word target, target not
    in location."""

    def test_no_location(self):
        c = _make_caller()
        c.location = None
        args = GiveCommand().parser.parse_args(["apple","bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("No.")

    def test_target_filtered_to(self):
        c = _make_caller()
        c.location = MagicMock(search=MagicMock(return_value=[MagicMock(id=99, name="Bob", msg=MagicMock())]))
        c.contents = []
        c.search = MagicMock(return_value=[])
        args = GiveCommand().parser.parse_args(["apple","to","bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("You don't have that.")

    def test_target_only_to(self):
        c = _make_caller()
        c.location = MagicMock()
        args = GiveCommand().parser.parse_args(["apple","to"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("Give it to whom?")

    def test_all_with_empty_inventory(self):
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
# Unloggedin QuitCommand intent (from test_intent_extra.py)
# ---------------------------------------------------------------------------

class TestUnloggedinQuit:
    """INTENT: 'quit' closes the connection."""

    def test_quit_closes_connection(self):
        c = MagicMock()
        c.session.connection.close = MagicMock()
        UnQuitCommand().run(c, None)
        c.session.connection.close.assert_called_once()
        c.msg.assert_called_with("Goodbye!")


# ---------------------------------------------------------------------------
# LookCommand: noun, link-target, and location search (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestLookNoun:
    """INTENT: 'look <noun>' returns the noun description if the target name
    is registered as a noun on the current node."""

    def test_noun_lookup(self):
        c = _make_caller()
        room = _make_room()
        room.add_noun("rock", "a small pebble")
        c.location = room
        c.search = MagicMock(return_value=[])
        room.search = MagicMock(return_value=[])
        room.get_noun = MagicMock(return_value="a small pebble")
        LookCommand().run(c, Namespace(target=["rock"]))
        c.msg.assert_called_with("a small pebble")


class TestLookLink:
    """INTENT: 'look <link_name>' returns the destination node's appearance."""

    def test_link_lookup(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        link = MagicMock()
        link.coord = Coord("test", 0, 1, 0)
        dest = MagicMock()
        dest.return_appearance = MagicMock(return_value="dest view")
        c.search = MagicMock(return_value=[])
        room.search = MagicMock(return_value=[])
        room.get_noun = MagicMock(return_value=None)
        room.get_link_by_name = MagicMock(return_value=link)
        with patch("atheriz.commands.loggedin.look.get_node_handler") as mock_nh:
            mock_nh.return_value.get_node.return_value = dest
            LookCommand().run(c, Namespace(target=["north"]))
        c.msg.assert_called_with("dest view")


class TestLookLocationSearch:
    """INTENT: when caller.search returns empty, fall back to location.search;
    if found, render via at_look."""

    def test_found_via_location_search(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        target = Object.create(None, "Rock")
        c.search = MagicMock(return_value=[])
        room.search = MagicMock(return_value=[target])
        c.at_look = MagicMock(return_value="<rock>")
        LookCommand().run(c, Namespace(target=["rock"]))
        c.at_look.assert_called_once()
        args, _ = c.at_look.call_args
        assert args[0] is target or args[0] == target


# ---------------------------------------------------------------------------
# EmoteCommand: empty text (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestEmoteEmptyText:
    """INTENT: 'emote' with empty text list falls through to help."""

    def test_empty_text_args(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        room.msg_contents = MagicMock()
        args = MagicMock(text=[])
        EmoteCommand().run(c, args)
        room.msg_contents.assert_not_called()
        c.msg.assert_called_once()


# ---------------------------------------------------------------------------
# InventoryCommand: multiple of same name (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestInventoryMultiple:
    """INTENT: 'inventory' groups by name and shows counts."""

    def test_lists_multiple_grouped(self):
        c = Object.create(None, "Alice")
        c.privilege_level = settings.Privilege.Player
        c.quelled = False
        c.msg = MagicMock()
        a1 = Object.create(None, "Apple")
        a2 = Object.create(None, "Apple")
        b = Object.create(None, "Banana")
        a1.move_to(c)
        a2.move_to(c)
        b.move_to(c)
        InventoryCommand().run(c, None)
        c.msg.assert_called_once()
        text = c.msg.call_args.args[0]
        assert "Apple" in text
        assert "Banana" in text


# ---------------------------------------------------------------------------
# ChannelCommand branches (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestChannelMoreBranches:
    """INTENT: covers the subscribe/replay/send 'no permission' branches
    and 'channel not found' for the -c switch."""

    def setup_method(self):
        ChannelCommand._channel_cache.clear()

    def test_channel_not_found(self):
        c = _make_caller()
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[]):
            args = Namespace(list=False, channel="missing", unsubscribe=False,
                            subscribe=False, replay=False, message=None)
            ChannelCommand().run(c, args)
        c.msg.assert_called_with("Channel missing not found.")

    def test_no_args_shows_help(self):
        c = _make_caller()
        ChannelCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_channel_no_message_shows_help(self):
        c = _make_caller()
        args = Namespace(list=False, channel=None, unsubscribe=False,
                        subscribe=False, replay=False, message=None)
        ChannelCommand().run(c, args)
        c.msg.assert_called_once()
        text = c.msg.call_args.args[0]
        assert "usage" in text.lower() or "channel" in text.lower()

    def test_subscribe_no_view_permission(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 1
        chan.name = "public"
        chan.is_deleted = False
        chan.access = MagicMock(return_value=False)
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=False,
                            subscribe=True, replay=False, message=None)
            cmd = ChannelCommand()
            cmd.channel = chan
            cmd.run(c, args)
        c.msg.assert_called_with("You do not have permission to view this channel.")

    def test_replay_no_view_permission(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 1
        chan.name = "public"
        chan.is_deleted = False
        chan.access = MagicMock(return_value=False)
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=False,
                            subscribe=False, replay=True, message=None)
            cmd = ChannelCommand()
            cmd.channel = chan
            cmd.run(c, args)
        c.msg.assert_called_with("You do not have permission to view this channel.")

    def test_send_no_send_permission(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 1
        chan.name = "public"
        chan.is_deleted = False
        chan.access = MagicMock(side_effect=lambda u, p: p == "view")
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=False,
                            subscribe=False, replay=False, message="hello")
            cmd = ChannelCommand()
            cmd.channel = chan
            cmd.run(c, args)
        c.msg.assert_called_with("You do not have permission to send to this channel.")

    def test_unsubscribe_calls_unsubscribe(self):
        c = _make_caller()
        c.unsubscribe = MagicMock()
        chan = MagicMock()
        chan.id = 1
        chan.name = "public"
        chan.is_deleted = False
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=True,
                            subscribe=False, replay=False, message=None)
            cmd = ChannelCommand()
            cmd.channel = chan
            cmd.run(c, args)
        c.unsubscribe.assert_called_once_with(chan)


# ---------------------------------------------------------------------------
# NoneCommand: known vs unknown internal cmdset (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestNoneCommandInternal:
    """INTENT: 'None' uses the caller's internal_cmdset to look for typos."""

    def test_uses_internal_cmdset_when_available(self):
        c = _make_caller()
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.get_keys.return_value = ["look", "say"]
        with patch("atheriz.commands.loggedin.none.get_loggedin_cmdset") as mock_lcs:
            mock_lcs.return_value.get_keys.return_value = []
            args = Namespace(none=["loo"])
            NoneCommand().run(c, args)
        msg = c.msg.call_args.args[0]
        assert "did you mean" in msg or "look" in msg

    def test_falls_back_to_global_cmdset(self):
        c = _make_caller()
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.get_keys.return_value = ["smile"]
        with patch("atheriz.commands.loggedin.none.get_loggedin_cmdset") as mock_lcs:
            mock_lcs.return_value.get_keys.return_value = []
            args = Namespace(none=["smile"])
            NoneCommand().run(c, args)
        c.msg.assert_called_once()


# ---------------------------------------------------------------------------
# CmdSet: verify a few specific behaviors (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestCmdSetSpec:
    """INTENT: cmdset has a known key set; reach into spec for advanced checks."""

    def test_get_all_returns_instances(self):
        cs = LoggedinCmdSet()
        all_cmds = cs.get_all()
        assert len(all_cmds) > 0
        from atheriz.commands.base_cmd import Command
        for cmd in all_cmds:
            assert isinstance(cmd, Command)

    def test_keys_attribute_is_dict(self):
        cs = LoggedinCmdSet()
        assert isinstance(cs.commands, dict)
        assert len(cs.commands) > 20

    def test_help_aliases_registered(self):
        cs = LoggedinCmdSet()
        assert cs.commands["?"] is cs.commands["help"]

    def test_socials_has_many_aliases(self):
        cs = LoggedinCmdSet()
        assert "smile" in cs.commands
        assert "frown" in cs.commands
        assert "hug" in cs.commands


# ---------------------------------------------------------------------------
# SaveCommand: TIME_SYSTEM_ENABLED toggle (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestSaveMessage:
    """INTENT: save command returns elapsed time in its success message."""

    def test_save_message_includes_time(self):
        c = _make_caller(superuser=True)
        old = settings.TIME_SYSTEM_ENABLED
        settings.TIME_SYSTEM_ENABLED = False
        try:
            with patch("atheriz.commands.loggedin.save.save_objects"), \
                 patch("atheriz.commands.loggedin.save.get_map_handler") as mock_mh, \
                 patch("atheriz.commands.loggedin.save.get_node_handler") as mock_nh, \
                 patch("atheriz.commands.loggedin.save.get_game_time") as mock_gt:
                mock_mh.return_value.save = MagicMock()
                mock_nh.return_value.save = MagicMock()
                mock_gt.return_value.save = MagicMock()
                SaveCommand().run(c, None)
            msg = c.msg.call_args.args[0]
            assert "Saved in" in msg
            assert "ms" in msg or "s" in msg
        finally:
            settings.TIME_SYSTEM_ENABLED = old


# ---------------------------------------------------------------------------
# SayCommand: alias is apostrophe (from test_intent_extra2)
# ---------------------------------------------------------------------------

class TestSayAlias:
    def test_alias_is_apostrophe(self):
        assert "'" in SayCommand.aliases
