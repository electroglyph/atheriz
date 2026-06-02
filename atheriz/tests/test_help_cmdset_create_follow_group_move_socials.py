"""Intent-focused tests for help, cmdset, create, socials, follow, group, move.

INTENT: Each test class documents the *behavior* of the command under test
and uses an INTENT docstring to capture the user-visible contract.
"""
from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.cmdset import LoggedinCmdSet
from atheriz.commands.loggedin.create import CreateCommand
from atheriz.commands.loggedin.follow import FollowCommand, NoFollowCommand
from atheriz.commands.loggedin.group import GroupCommand
from atheriz.commands.loggedin.help import HelpCommand
from atheriz.commands.loggedin.move import MoveCommand
from atheriz.commands.loggedin.socials import CmdSocials, SOCIALS_DICT
from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet
from atheriz.commands.unloggedin.help import HelpCommand as UnHelpCommand
from atheriz.globals.objects import _ALL_OBJECTS
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def _make_caller(name="Alice", builder=False, screenreader=False, term_width=80):
    c = MagicMock(spec=Object)
    c.name = name
    c.id = 1
    c.privilege_level = settings.Privilege.Builder if builder else settings.Privilege.Player
    c.quelled = False
    c.no_follow = False
    c.following = None
    c.followers = set()
    c.group_channel = None
    c.session = MagicMock()
    c.session.screenreader = screenreader
    c.session.term_width = term_width
    c.msg = MagicMock()
    c.location = None
    c.contents = []
    return c


# ---------------------------------------------------------------------------
# HelpCommand (loggedin)
# ---------------------------------------------------------------------------

class TestLoggedinHelpCommand:
    """INTENT: help lists accessible commands in a pretty table; ? is alias;
    with no args lists all accessible commands, with a name shows that
    command's help or 'Command not found.'."""

    def test_alias_is_question_mark(self):
        assert "?" in HelpCommand().aliases

    def test_no_args_lists_commands(self):
        c = _make_caller()
        HelpCommand().run(c, Namespace(command=None))
        c.msg.assert_called_once()
        text = c.msg.call_args[0][0]
        assert "Category" in text

    def test_screenreader_skips_borders(self):
        c = _make_caller(screenreader=True)
        HelpCommand().run(c, Namespace(command=None))
        c.msg.assert_called_once()
        # The PrettyTable with border=False is used - just verify no crash

    def test_help_for_existing_command(self):
        c = _make_caller()
        # 'look' is in the loggedin cmdset and accessible to players
        HelpCommand().run(c, Namespace(command="look"))
        c.msg.assert_called_once()

    def test_help_for_missing_command(self):
        c = _make_caller()
        HelpCommand().run(c, Namespace(command="notreal"))
        c.msg.assert_called_with("Command not found.")


# ---------------------------------------------------------------------------
# HelpCommand (unloggedin)
# ---------------------------------------------------------------------------

class TestUnloggedinHelpCommand:
    """INTENT: unloggedin help lists connect/guest/etc, and 'Command not found.'
    for invalid input. No local_cmdset support since callers are pre-login."""

    def test_no_args_lists_unloggedin_commands(self):
        c = _make_caller()
        UnHelpCommand().run(c, Namespace(command=None))
        c.msg.assert_called_once()

    def test_help_for_connect(self):
        c = _make_caller()
        UnHelpCommand().run(c, Namespace(command="connect"))
        c.msg.assert_called_once()

    def test_help_for_missing(self):
        c = _make_caller()
        UnHelpCommand().run(c, Namespace(command="notreal"))
        c.msg.assert_called_with("Command not found.")


# ---------------------------------------------------------------------------
# LoggedinCmdSet
# ---------------------------------------------------------------------------

class TestLoggedinCmdSet:
    """INTENT: registering the cmdset must include all required commands."""

    def test_registers_look(self):
        cs = LoggedinCmdSet()
        assert "look" in cs.commands

    def test_registers_help_with_alias(self):
        cs = LoggedinCmdSet()
        assert "help" in cs.commands
        assert "?" in cs.commands

    def test_registers_socials_with_aliases(self):
        cs = LoggedinCmdSet()
        # smile is an alias of socials
        assert "socials" in cs.commands
        assert "smile" in cs.commands

    def test_registers_quell_and_unquell(self):
        cs = LoggedinCmdSet()
        assert "quell" in cs.commands
        assert "unquell" in cs.commands

    def test_registers_open_close_lock_unlock(self):
        cs = LoggedinCmdSet()
        for k in ("open", "close", "lock", "unlock"):
            assert k in cs.commands

    def test_registers_follow_nofollow_group(self):
        cs = LoggedinCmdSet()
        for k in ("follow", "nofollow", "group"):
            assert k in cs.commands


# ---------------------------------------------------------------------------
# UnloggedinCmdSet
# ---------------------------------------------------------------------------

class TestUnloggedinCmdSet:
    """INTENT: unloggedin set includes auth commands and a help system."""

    def test_registers_connect_guest_quit(self):
        cs = UnloggedinCmdSet()
        for k in ("connect", "guest", "quit"):
            assert k in cs.commands

    def test_registers_help_and_screenreader(self):
        cs = UnloggedinCmdSet()
        assert "help" in cs.commands
        assert "screenreader" in cs.commands


# ---------------------------------------------------------------------------
# CreateCommand
# ---------------------------------------------------------------------------

class TestCreateCommand:
    """INTENT: builder-only command to spawn a new Object with a name and
    optional type flags. Created object is moved into caller's inventory."""

    def test_access_requires_builder(self):
        c = _make_caller()
        c.is_builder = False
        assert CreateCommand().access(c) is False

    def test_access_allowed_for_builder(self):
        c = _make_caller()
        c.is_builder = True
        assert CreateCommand().access(c) is True

    def test_no_args_shows_help(self):
        c = _make_caller(builder=True)
        CreateCommand().run(c, None)
        c.msg.assert_called_once()

    def test_creates_object(self):
        c = _make_caller(builder=True)
        args = Namespace(name="Orb", is_pc=False, is_item=True, is_npc=False,
                        is_mapable=False, is_container=False, is_tickable=False, desc=["a","glowing","orb"])
        with patch("atheriz.objects.base_obj.Object.create") as mock_create:
            new_obj = MagicMock()
            new_obj.name = "Orb"
            new_obj.id = 999
            new_obj.move_to = MagicMock()
            mock_create.return_value = new_obj
            CreateCommand().run(c, args)
        mock_create.assert_called_once()
        kw = mock_create.call_args.kwargs
        assert kw["name"] == "Orb"
        assert kw["desc"] == "a glowing orb"
        assert kw["is_item"] is True
        new_obj.move_to.assert_called_once_with(c)
        c.msg.assert_called_once()
        assert "Orb" in c.msg.call_args[0][0]

    def test_empty_desc_uses_blank(self):
        c = _make_caller(builder=True)
        args = Namespace(name="Rock", is_pc=False, is_item=True, is_npc=False,
                        is_mapable=False, is_container=False, is_tickable=False, desc=[])
        with patch("atheriz.objects.base_obj.Object.create") as mock_create:
            new_obj = MagicMock()
            new_obj.name = "Rock"
            new_obj.id = 999
            mock_create.return_value = new_obj
            CreateCommand().run(c, args)
        assert mock_create.call_args.kwargs["desc"] == ""


# ---------------------------------------------------------------------------
# FollowCommand / NoFollowCommand
# ---------------------------------------------------------------------------

class TestFollowCommand:
    """INTENT: 'follow <name>' sets caller.following = target.id; a FollowScript
    is created on the target to track movement. Builder bypasses no_follow.
    'nofollow' toggles caller.no_follow and disbands existing followers."""

    def test_no_args_msg(self):
        c = _make_caller()
        FollowCommand().run(c, None)
        c.msg.assert_called_with("Follow who?")

    def test_target_not_found(self):
        c = _make_caller()
        c.search = MagicMock(return_value=[])
        c.location = MagicMock(access=lambda *a, **k: True, search=MagicMock(return_value=[]))
        FollowCommand().run(c, Namespace(target="ghost"))
        assert any("Could not find" in str(call) for call in c.msg.call_args_list)

    def test_cannot_follow_self(self):
        c = _make_caller()
        c.id = 1
        # target.__eq__ returns True for caller so the `target == caller` check matches
        target = MagicMock()
        target.id = 1
        target.name = "Alice"
        target.__eq__ = lambda self, other: other is c
        c.search = MagicMock(return_value=[target])
        FollowCommand().run(c, Namespace(target="me"))
        c.msg.assert_called_with("You can't follow yourself!")

    def test_cannot_follow_non_pc_npc(self):
        c = _make_caller()
        target = MagicMock()
        target.id = 99
        target.is_pc = False
        target.is_npc = False
        target.name = "Rock"
        c.search = MagicMock(return_value=[target])
        FollowCommand().run(c, Namespace(target="rock"))
        c.msg.assert_called_with("You can't follow that!")

    def test_target_blocks_with_no_follow(self):
        c = _make_caller()
        c.is_builder = False
        target = MagicMock()
        target.id = 99
        target.is_pc = True
        target.is_npc = False
        target.no_follow = True
        target.name = "Bob"
        c.search = MagicMock(return_value=[target])
        FollowCommand().run(c, Namespace(target="bob"))
        c.msg.assert_called_with("Bob will not lead you.")

    def test_already_following(self):
        c = _make_caller()
        target = MagicMock()
        target.id = 99
        target.is_pc = True
        target.is_npc = False
        target.no_follow = False
        target.name = "Bob"
        target.get_scripts_by_type = MagicMock(return_value=[])
        target.add_script = MagicMock()
        target.lock = MagicMock()
        target.followers = set()
        target.access = MagicMock(return_value=True)
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock(access=MagicMock(return_value=True))
        c.following = 99
        FollowCommand().run(c, Namespace(target="bob"))
        c.msg.assert_called_with("You are already following Bob!")

    def test_successful_follow(self):
        c = _make_caller()
        target = MagicMock()
        target.id = 99
        target.is_pc = True
        target.is_npc = False
        target.no_follow = False
        target.name = "Bob"
        target.get_scripts_by_type = MagicMock(return_value=[])
        target.add_script = MagicMock()
        target.lock = MagicMock()
        target.followers = set()
        target.access = MagicMock(return_value=True)
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock(access=MagicMock(return_value=True), msg_contents=MagicMock())
        FollowCommand().run(c, Namespace(target="bob"))
        assert c.following == 99
        assert 1 in target.followers
        target.add_script.assert_called_once()


class TestNoFollowCommand:
    """INTENT: nofollow toggles caller.no_follow; when enabling, immediately
    disbands existing followers (builders are exempt)."""

    def test_disable(self):
        c = _make_caller()
        c.no_follow = True
        c.followers = set()
        c.get_scripts_by_type = MagicMock(return_value=[])
        c.lock = MagicMock()
        c.access = MagicMock(return_value=True)
        NoFollowCommand().run(c, None)
        assert c.no_follow is False
        c.msg.assert_called_with("You will now allow others to follow you.")

    def test_enable_disbands(self):
        c = _make_caller()
        c.no_follow = False
        c.followers = {1, 2}
        c.get_scripts_by_type = MagicMock(return_value=[])
        c.lock = MagicMock()
        c.access = MagicMock(return_value=True)
        # Make get() return real-looking followers
        f1 = MagicMock()
        f1.is_builder = False
        f1.lock = MagicMock()
        f1.following = 99
        f1.access = MagicMock(return_value=True)
        f1.get_display_name = MagicMock(return_value="F1")
        f1.msg = MagicMock()
        f2 = MagicMock()
        f2.is_builder = True
        with patch("atheriz.commands.loggedin.follow.get") as mock_get:
            mock_get.side_effect = lambda x: [f1] if x == 1 else ([f2] if x == 2 else [])
            NoFollowCommand().run(c, None)
        assert c.no_follow is True
        # The disband message is the *first* call (before the per-follower "You are no longer leading" messages)
        assert c.msg.call_args_list[0].args == ("You will no longer allow others to follow you.",)


# ---------------------------------------------------------------------------
# GroupCommand
# ---------------------------------------------------------------------------

class TestGroupCommand:
    """INTENT: 'group <subcmd>' manages a private channel where the leader
    is the creator. 'list', 'add', 'kick', 'leave', or a default <message>."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        GroupCommand().run(c, Namespace(args=[]))
        c.msg.assert_called_once()

    def test_list_when_not_in_group(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["list"]))
        c.msg.assert_called_with("You are not in a group.")

    def test_kick_usage(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["kick"]))
        c.msg.assert_called_with("Usage: group kick <name>")

    def test_leave_when_not_in_group(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["leave"]))
        c.msg.assert_called_with("You are not in a group.")

    def test_add_usage(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["add"]))
        c.msg.assert_called_with("Usage: group add <name>")

    def test_add_target_not_following(self):
        c = _make_caller()
        target = MagicMock()
        target.id = 50
        target.get_display_name = MagicMock(return_value="Bob")
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock(access=MagicMock(return_value=True))
        c.lock = MagicMock()
        c.followers = set()  # target is not in followers
        GroupCommand().run(c, Namespace(args=["add", "bob"]))
        c.msg.assert_called_with("Bob is not following you.")

    def test_add_self(self):
        c = _make_caller()
        c.search = MagicMock(return_value=[c])
        c.location = MagicMock(access=MagicMock(return_value=True))
        GroupCommand().run(c, Namespace(args=["add", "me"]))
        c.msg.assert_called_with("You can't add yourself!")

    def test_default_message_when_not_in_group(self):
        c = _make_caller()
        c.group_channel = None
        GroupCommand().run(c, Namespace(args=["hello","team"]))
        c.msg.assert_called_with("You are not in a group.")


# ---------------------------------------------------------------------------
# MoveCommand
# ---------------------------------------------------------------------------

class TestMoveCommand:
    """INTENT: builder-only command to teleport to any node by (area,x,y,z).
    Force-move bypasses locks. Format: 'move area x y z' or 'move (a,x,y,z)'."""

    def test_access_requires_builder(self):
        c = _make_caller()
        c.is_builder = False
        assert MoveCommand().access(c) is False

    def test_access_allowed_for_builder(self):
        c = _make_caller()
        c.is_builder = True
        assert MoveCommand().access(c) is True

    def test_no_args_shows_help(self):
        c = _make_caller(builder=True)
        MoveCommand().run(c, None)
        c.msg.assert_called_once()

    def test_wrong_arity(self):
        c = _make_caller(builder=True)
        MoveCommand().run(c, Namespace(coord=["a","b"]))
        c.msg.assert_called_with("Usage: move <area> <x> <y> <z>  or  move (<area>,<x>,<y>,<z>)")

    def test_non_integer_xy(self):
        c = _make_caller(builder=True)
        MoveCommand().run(c, Namespace(coord=["area","x","y","z"]))
        c.msg.assert_called_with("x, y, and z must be integers.")

    def test_no_node_at_coord(self):
        c = _make_caller(builder=True)
        with patch("atheriz.commands.loggedin.move.get_node_handler") as mock_nh:
            mock_nh.return_value.get_node.return_value = None
            MoveCommand().run(c, Namespace(coord=["limbo","0","0","0"]))
        assert any("No node found at" in str(call) for call in c.msg.call_args_list)

    def test_successful_move(self):
        c = _make_caller(builder=True)
        node = MagicMock()
        node.coord = Coord("area", 1, 2, 3)
        node.desc = ""
        with patch("atheriz.commands.loggedin.move.get_node_handler") as mock_nh:
            mock_nh.return_value.get_node.return_value = node
            MoveCommand().run(c, Namespace(coord=["area","1","2","3"]))
        c.move_to.assert_called_once()
        assert "Moved to" in c.msg.call_args[0][0]

    def test_paren_format(self):
        c = _make_caller(builder=True)
        node = MagicMock()
        node.coord = Coord("area", 5, 6, 7)
        node.desc = ""
        with patch("atheriz.commands.loggedin.move.get_node_handler") as mock_nh:
            mock_nh.return_value.get_node.return_value = node
            MoveCommand().run(c, Namespace(coord=["(area,5,6,7)"]))
        c.move_to.assert_called_once()


# ---------------------------------------------------------------------------
# CmdSocials (additional intent tests)
# ---------------------------------------------------------------------------

class TestCmdSocialsExtra:
    """INTENT: covers the 'socials' (literal) and 'no matching template' branches."""

    def test_socials_command_lists_aliases(self):
        c = _make_caller()
        args = Namespace(cmdstring="socials", target=[])
        CmdSocials().run(c, args)
        c.msg.assert_called_once()
        text = c.msg.call_args[0][0]
        assert "smile" in text
        assert "hug" in text

    def test_unknown_cmdstring_uses_invocation_msg(self):
        c = _make_caller()
        c.location = MagicMock()
        c.location.msg_contents = MagicMock()
        args = Namespace(cmdstring="laugh", target=[])
        CmdSocials().run(c, args)
        c.location.msg_contents.assert_called_once()

    def test_all_socials_have_two_templates(self):
        for verb, templates in SOCIALS_DICT.items():
            assert isinstance(templates, tuple), f"{verb} not tuple"
            assert len(templates) == 2, f"{verb} does not have 2 templates"
            assert "$You" in templates[0]
            assert "$You" in templates[1]

    def test_targeted_social_template_is_used(self):
        c = _make_caller()
        target = MagicMock()
        target.id = 99
        target.is_pc = True
        target.is_npc = False
        c.search = MagicMock(return_value=target)
        c.location = MagicMock()
        c.location.msg_contents = MagicMock()
        args = Namespace(cmdstring="wave", target=["Bob"])
        CmdSocials().run(c, args)
        c.location.msg_contents.assert_called_once()
        kwargs = c.location.msg_contents.call_args.kwargs
        assert "target" in kwargs["mapping"]
        assert kwargs["mapping"]["target"] is target
