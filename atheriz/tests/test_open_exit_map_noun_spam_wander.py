"""Tests for the remaining commands: open, close, lock, unlock, exit, map, noun, spam, wander, unloggedin none."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.map import MapCommand
from atheriz.commands.loggedin.noun import NounCommand
from atheriz.commands.loggedin.open import CloseCommand, LockCommand, OpenCommand, UnlockCommand
from atheriz.commands.loggedin.spam import SpamCommand
from atheriz.commands.loggedin.wander import WanderCommand
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.commands.unloggedin.none import NoneCommand as UnloggedinNoneCommand
from atheriz.globals.objects import add_object, get
from atheriz.globals.get import get_node_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeArea, NodeGrid, NodeLink
from atheriz.utils import Coord


def _make_caller(name="Alice", builder=False, superuser=False, session=None, location=None):
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
    c.location = location
    c.session = session or MagicMock(screenreader=False, term_width=80, term_height=24)
    return c


def _make_coord(area="t", x=0, y=0, z=0):
    return Coord(area, x, y, z)


def _add_node(nh, coord, desc="Room"):
    node = Node(coord=coord, desc=desc)
    nh.add_node(node)
    return node


# ---------------------------------------------------------------------------
# OpenCommand / CloseCommand / LockCommand / UnlockCommand
# ---------------------------------------------------------------------------

class TestOpenCommand:
    """INTENT: open door in a given direction via Door.try_open."""

    def test_no_location(self):
        c = _make_caller()
        c.location = None
        OpenCommand().run(c, MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[]))
        c.msg.assert_called_with("You have an invalid location.")

    def test_no_direction(self):
        coord = _make_coord()
        c = _make_caller(location=Node(coord=coord))
        OpenCommand().run(c, MagicMock(north=False, south=False, east=False, west=False, up=False, down=False, args=[]))
        # "Open what?" is the first call, followed by print_help()
        first_call_args = c.msg.call_args_list[0].args
        assert first_call_args == ("Open what?",)

    def test_directional_text_north(self):
        coord = _make_coord()
        c = _make_caller(location=Node(coord=coord))
        # Pass "north" via args (positional string)
        args = MagicMock(north=False, south=False, east=False, west=False, up=False, down=False, args=["north"])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = None
            OpenCommand().run(c, args)
        c.msg.assert_called_with("There is no door to the north.")

    def test_opens_door(self):
        coord = _make_coord()
        loc = Node(coord=coord)
        c = _make_caller(location=loc)
        door = MagicMock()
        door.try_open = MagicMock()
        args = MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = {"north": door, "n": door}
            OpenCommand().run(c, args)
        door.try_open.assert_called_once_with(c)


class TestCloseCommand:
    def test_no_location(self):
        c = _make_caller()
        c.location = None
        CloseCommand().run(c, MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[]))
        c.msg.assert_called_with("You have an invalid location.")

    def test_no_direction(self):
        c = _make_caller(location=Node(coord=_make_coord()))
        CloseCommand().run(c, MagicMock(north=False, south=False, east=False, west=False, up=False, down=False, args=[]))
        # "Close what?" is the first call, followed by print_help()
        first_call_args = c.msg.call_args_list[0].args
        assert first_call_args == ("Close what?",)

    def test_closes_door(self):
        coord = _make_coord()
        loc = Node(coord=coord)
        c = _make_caller(location=loc)
        door = MagicMock()
        door.try_close = MagicMock()
        args = MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = {"north": door}
            CloseCommand().run(c, args)
        door.try_close.assert_called_once_with(c)

    def test_no_door(self):
        coord = _make_coord()
        loc = Node(coord=coord)
        c = _make_caller(location=loc)
        args = MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = {}
            CloseCommand().run(c, args)
        c.msg.assert_called_with("There is no door to the north.")


class TestLockCommand:
    def test_no_location(self):
        c = _make_caller()
        c.location = None
        LockCommand().run(c, MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[]))
        c.msg.assert_called_with("You have an invalid location.")

    def test_locks_door(self):
        coord = _make_coord()
        c = _make_caller(location=Node(coord=coord))
        door = MagicMock()
        door.try_lock = MagicMock()
        args = MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = {"north": door}
            LockCommand().run(c, args)
        door.try_lock.assert_called_once_with(c)

    def test_no_door(self):
        coord = _make_coord()
        c = _make_caller(location=Node(coord=coord))
        args = MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = None
            LockCommand().run(c, args)
        c.msg.assert_called_with("There is no door to the north.")


class TestUnlockCommand:
    def test_no_location(self):
        c = _make_caller()
        c.location = None
        UnlockCommand().run(c, MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[]))
        c.msg.assert_called_with("You have an invalid location.")

    def test_unlocks_door(self):
        coord = _make_coord()
        c = _make_caller(location=Node(coord=coord))
        door = MagicMock()
        door.try_unlock = MagicMock()
        args = MagicMock(north=True, south=False, east=False, west=False, up=False, down=False, args=[])
        with patch("atheriz.commands.loggedin.open.get_node_handler") as mock_nh:
            mock_nh.return_value.get_doors.return_value = {"north": door}
            UnlockCommand().run(c, args)
        door.try_unlock.assert_called_once_with(c)


# ---------------------------------------------------------------------------
# MapCommand
# ---------------------------------------------------------------------------

class TestMapCommand:
    """INTENT: toggles map_enabled and sends map_enable/map_disable tag."""

    def test_enables(self):
        c = _make_caller()
        c.map_enabled = False
        MapCommand().run(c, None)
        assert c.map_enabled is True
        c.msg.assert_any_call("Map enabled.")
        c.msg.assert_any_call(map_enable="")

    def test_disables(self):
        c = _make_caller()
        c.map_enabled = True
        MapCommand().run(c, None)
        assert c.map_enabled is False
        c.msg.assert_any_call("Map disabled.")
        c.msg.assert_any_call(map_disable="")

    def test_toggle_twice(self):
        c = _make_caller()
        c.map_enabled = False
        MapCommand().run(c, None)
        assert c.map_enabled is True
        MapCommand().run(c, None)
        assert c.map_enabled is False


# ---------------------------------------------------------------------------
# NounCommand
# ---------------------------------------------------------------------------

class TestNounCommand:
    """INTENT: builder-only; add/update noun description on a node."""

    def test_access_requires_builder(self):
        c = _make_caller(builder=False)
        assert NounCommand().access(c) is False

    def test_access_allowed_for_builder(self):
        c = _make_caller(builder=True)
        assert NounCommand().access(c) is True

    def test_no_args_shows_help(self):
        c = _make_caller(builder=True)
        NounCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location(self):
        c = _make_caller(builder=True, location=None)
        args = MagicMock(noun="rock", desc=["a", "boulder"])
        NounCommand().run(c, args)
        c.msg.assert_called_with("No.")

    def test_adds_new_noun(self):
        loc = Node(coord=_make_coord())
        c = _make_caller(builder=True, location=loc)
        args = MagicMock(noun="rock", desc=["a", "stone"])
        NounCommand().run(c, args)
        assert loc.get_noun("rock") == "a stone"
        c.msg.assert_called_with("Added 'rock'.")

    def test_updates_existing_noun(self):
        loc = Node(coord=_make_coord())
        loc.add_noun("rock", "an old stone")
        c = _make_caller(builder=True, location=loc)
        args = MagicMock(noun="rock", desc=["a", "new", "stone"])
        NounCommand().run(c, args)
        assert loc.get_noun("rock") == "a new stone"
        c.msg.assert_called_with("Updated 'rock'.")


# ---------------------------------------------------------------------------
# ExitCommand
# ---------------------------------------------------------------------------

class TestExitCommand:
    """INTENT: moves a caller from a node to a destination; auto-opens/closes doors."""

    def test_move_through_door_open_path(self):
        # create source and dest
        nh = get_node_handler()
        src_coord = _make_coord("a", 0, 0, 0)
        dest_coord = _make_coord("a", 0, 2, 0)
        src = _add_node(nh, src_coord, "src")
        dest = _add_node(nh, dest_coord, "dest")
        caller = Object.create(None, "Eve", is_pc=True)
        add_object(caller)
        caller.location = src
        # Patch move_to on the real Object
        from atheriz.objects.base_obj import Object as RealObject
        with patch.object(RealObject, "move_to", return_value=True) as mock_move:
            ex = ExitCommand()
            ex.caller_id = caller.id
            ex.location = src_coord
            ex.destination = dest_coord
            ex.name = "north"
            with patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
                # No doors registered
                nh.doors.clear()
                ex.do_move()
        mock_move.assert_called_once()

    def test_no_destination(self):
        nh = get_node_handler()
        ex = ExitCommand()
        ex.caller_id = -1
        ex.location = _make_coord("a", 0, 0, 0)
        ex.destination = _make_coord("a", 0, 2, 0)
        ex.name = "north"
        with patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh), \
             patch("atheriz.commands.loggedin.exit.get", return_value=[]) as mock_get:
            ex.do_move()  # should not raise


# ---------------------------------------------------------------------------
# SpamCommand
# ---------------------------------------------------------------------------

class TestSpamCommand:
    """INTENT: superuser-only; bulk-creates accounts/chars; respects cap."""

    def test_access_requires_superuser(self):
        c = _make_caller(superuser=False)
        assert SpamCommand().access(c) is False

    def test_access_allowed_for_superuser(self):
        c = _make_caller(superuser=True)
        assert SpamCommand().access(c) is True

    def test_no_args(self):
        c = _make_caller(superuser=True)
        SpamCommand().run(c, None)
        c.msg.assert_called_with("Usage: spam <count>")

    def test_too_many(self):
        c = _make_caller(superuser=True)
        args = MagicMock(count=1001)
        SpamCommand().run(c, args)
        c.msg.assert_called_with("Maximum count is 1000.")

    def test_creates_accounts(self, tmp_path, fixed_salt):
        # INTENT: count=2 creates 2 accounts and writes spam_accounts.txt
        c = _make_caller(superuser=True)
        c.location = MagicMock()
        args = MagicMock(count=2)
        from atheriz import settings as s
        save_path = tmp_path
        with patch.object(s, "SAVE_PATH", str(save_path)), \
             patch("atheriz.commands.loggedin.spam.get_node_handler") as mock_nh, \
             patch("atheriz.commands.loggedin.spam.save_objects") as mock_save:
            mock_nh.return_value = MagicMock()
            SpamCommand().run(c, args)
        assert (save_path / "spam_accounts.txt").exists()
        content = (save_path / "spam_accounts.txt").read_text()
        assert "account1" in content
        assert "account2" in content
        assert "char1" in content
        assert "char2" in content

    def test_skips_existing(self, tmp_path):
        c = _make_caller(superuser=True)
        c.location = MagicMock()
        from atheriz import settings as s
        with patch.object(s, "SAVE_PATH", str(tmp_path)), \
             patch("atheriz.commands.loggedin.spam.get_node_handler") as mock_nh, \
             patch("atheriz.commands.loggedin.spam.save_objects"), \
             patch("atheriz.commands.loggedin.spam.Account.create",
                   side_effect=ValueError("Account with this name (account1) already exists.")):
            mock_nh.return_value = MagicMock()
            args = MagicMock(count=1)
            SpamCommand().run(c, args)
        # "skipping" message should have been emitted
        assert any("skipping" in str(call) for call in c.msg.call_args_list)


# ---------------------------------------------------------------------------
# WanderCommand
# ---------------------------------------------------------------------------

class TestWanderCommand:
    """INTENT: builder-only; spawns N wanderer NPCs in current area."""

    def test_access_requires_builder(self):
        c = _make_caller(builder=False)
        assert WanderCommand().access(c) is False

    def test_access_allowed_for_builder(self):
        c = _make_caller(builder=True)
        assert WanderCommand().access(c) is True

    def test_not_in_node(self):
        c = _make_caller(builder=True, location=Object.create(None, "NotANode"))
        # Provide count=1
        args = MagicMock(count=1)
        WanderCommand().run(c, args)
        c.msg.assert_called_with("You must be in a room to spawn wanderers.")

    def test_spawns_in_node(self):
        nh = get_node_handler()
        coord = _make_coord("wander_test", 0, 0, 0)
        node = _add_node(nh, coord, "wt")
        c = _make_caller(builder=True, location=node)
        c.id = 1  # needed because Object.create uses caller.id
        args = MagicMock(count=1)
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh):
            WanderCommand().run(c, args)
        # Should have a confirmation about spawn
        assert any("Spawned" in str(call) for call in c.msg.call_args_list)


# ---------------------------------------------------------------------------
# Unloggedin NoneCommand
# ---------------------------------------------------------------------------

class TestUnloggedinNoneCommand:
    """INTENT: suggests closest known command via levenshtein distance."""

    def test_suggests_close_command(self):
        c = MagicMock()
        args = MagicMock(none=["quut"])  # typo of quit
        UnloggedinNoneCommand().run(c, args)
        # Should suggest a command
        assert c.msg.called
        msg = c.msg.call_args[0][0]
        assert "did you mean" in msg

    def test_suggests_long_typo(self):
        c = MagicMock()
        args = MagicMock(none=["connnect"])
        UnloggedinNoneCommand().run(c, args)
        assert c.msg.called
        assert "did you mean" in c.msg.call_args[0][0]
