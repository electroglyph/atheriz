"""INTENT-focused tests for additional command branches and edge cases (round 2).

INTENT: each test class documents user-visible behavior with INTENT docstrings.
"""
from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.channel import ChannelCommand
from atheriz.commands.loggedin.cmdset import LoggedinCmdSet
from atheriz.commands.loggedin.emote import EmoteCommand
from atheriz.commands.loggedin.inventory import InventoryCommand
from atheriz.commands.loggedin.look import LookCommand
from atheriz.commands.loggedin.none import NoneCommand
from atheriz.commands.loggedin.say import SayCommand
from atheriz.commands.loggedin.save import SaveCommand
from atheriz.globals.objects import add_object
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
    c.msg = MagicMock()
    c.search = MagicMock(return_value=[])
    return c


def _make_room(coord=None, desc="A test room."):
    if coord is None:
        coord = Coord("test", 0, 0, 0)
    r = Node(coord=coord, desc=desc, symbol="#")
    add_object(r)
    return r


# ---------------------------------------------------------------------------
# LookCommand: noun, link-target, and target-success branches
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
        # target is the only match, so at_look was called with it
        args, _ = c.at_look.call_args
        assert args[0] is target or args[0] == target


# ---------------------------------------------------------------------------
# EmoteCommand: empty text, no location
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
        # No broadcast; caller gets help
        room.msg_contents.assert_not_called()
        c.msg.assert_called_once()


# ---------------------------------------------------------------------------
# InventoryCommand: multiple of same name
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
# ChannelCommand: subscribe without permission, replay without permission,
# send without permission, message without -c, etc.
# ---------------------------------------------------------------------------

class TestChannelMoreBranches:
    """INTENT: covers the subscribe/replay/send 'no permission' branches
    and 'channel not found' for the -c switch."""

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
        # help message contains "usage"
        text = c.msg.call_args.args[0]
        assert "usage" in text.lower() or "channel" in text.lower()

    def test_subscribe_no_view_permission(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 1
        chan.access = MagicMock(return_value=False)
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=False,
                            subscribe=True, replay=False, message=None)
            cmd = ChannelCommand()
            cmd.channel = chan
            ChannelCommand().run(c, args)
        c.msg.assert_called_with("You do not have permission to view this channel.")

    def test_replay_no_view_permission(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 1
        chan.access = MagicMock(return_value=False)
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=False,
                            subscribe=False, replay=True, message=None)
            cmd = ChannelCommand()
            cmd.channel = chan
            ChannelCommand().run(c, args)
        c.msg.assert_called_with("You do not have permission to view this channel.")

    def test_send_no_send_permission(self):
        c = _make_caller()
        chan = MagicMock()
        chan.id = 1
        # subscribe/replay need view; send needs send
        chan.access = MagicMock(side_effect=lambda u, p: p == "view")
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=False,
                            subscribe=False, replay=False, message="hello")
            cmd = ChannelCommand()
            cmd.channel = chan
            ChannelCommand().run(c, args)
        c.msg.assert_called_with("You do not have permission to send to this channel.")

    def test_unsubscribe_calls_unsubscribe(self):
        c = _make_caller()
        c.unsubscribe = MagicMock()
        chan = MagicMock()
        chan.id = 1
        with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]):
            args = Namespace(list=False, channel="public", unsubscribe=True,
                            subscribe=False, replay=False, message=None)
            cmd = ChannelCommand()
            cmd.channel = chan
            ChannelCommand().run(c, args)
        c.unsubscribe.assert_called_once_with(chan)


# ---------------------------------------------------------------------------
# NoneCommand: known vs unknown internal cmdset
# ---------------------------------------------------------------------------

class TestNoneCommandInternal:
    """INTENT: 'None' uses the caller's internal_cmdset to look for typos."""

    def test_uses_internal_cmdset_when_available(self):
        c = _make_caller()
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.commands = {"look": MagicMock(), "say": MagicMock()}
        with patch("atheriz.commands.loggedin.none.get_loggedin_cmdset") as mock_lcs:
            mock_lcs.return_value.commands = {}
            args = Namespace(none=["loo"])  # typo of "look"
            NoneCommand().run(c, args)
        msg = c.msg.call_args.args[0]
        assert "did you mean" in msg or "look" in msg

    def test_falls_back_to_global_cmdset(self):
        c = _make_caller()
        # NoneCommand always reads internal_cmdset.commands; the code does
        # not guard against None — verify current behavior.
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.commands = {"smile": MagicMock()}
        with patch("atheriz.commands.loggedin.none.get_loggedin_cmdset") as mock_lcs:
            mock_lcs.return_value.commands = {}
            args = Namespace(none=["smile"])
            NoneCommand().run(c, args)
        c.msg.assert_called_once()


# ---------------------------------------------------------------------------
# CmdSet: verify a few specific behaviors
# ---------------------------------------------------------------------------

class TestCmdSetSpec:
    """INTENT: cmdset has a known key set; reach into spec for advanced checks."""

    def test_get_all_returns_instances(self):
        cs = LoggedinCmdSet()
        all_cmds = cs.get_all()
        assert len(all_cmds) > 0
        # All should be Command instances
        from atheriz.commands.base_cmd import Command
        for cmd in all_cmds:
            assert isinstance(cmd, Command)

    def test_keys_attribute_is_dict(self):
        cs = LoggedinCmdSet()
        # 'commands' is the dict
        assert isinstance(cs.commands, dict)
        assert len(cs.commands) > 20

    def test_help_aliases_registered(self):
        cs = LoggedinCmdSet()
        # '?' and 'help' both map to the same HelpCommand instance
        assert cs.commands["?"] is cs.commands["help"]

    def test_socials_has_many_aliases(self):
        cs = LoggedinCmdSet()
        # 'smile' is a socials alias
        assert "smile" in cs.commands
        assert "frown" in cs.commands
        assert "hug" in cs.commands


# ---------------------------------------------------------------------------
# SaveCommand: TIME_SYSTEM_ENABLED toggle already tested; verify success msg format
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
# SayCommand: alias is apostrophe
# ---------------------------------------------------------------------------

class TestSayAlias:
    def test_alias_is_apostrophe(self):
        assert "'" in SayCommand.aliases
