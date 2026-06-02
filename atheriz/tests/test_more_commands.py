"""Tests for loggedin commands: look, emote, get, drop, give, time, reload, shutdown, none."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.emote import EmoteCommand
from atheriz.commands.loggedin.give import GiveCommand
from atheriz.commands.loggedin.look import LookCommand
from atheriz.commands.loggedin.none import NoneCommand
from atheriz.commands.loggedin.reload import ReloadCommand
from atheriz.commands.loggedin.shutdown import ShutdownCommand
from atheriz.commands.loggedin.time import TimeCommand
from atheriz.globals.objects import add_object, get
from atheriz.objects.base_obj import Object
from atheriz.utils import Coord
from atheriz.objects.nodes import Node


def _make_caller(name="Alice", msg=None):
    c = Object.create(None, name)
    c.privilege_level = settings.Privilege.Player
    c.quelled = False
    c.msg = msg or MagicMock()
    c.search = Object.search.__get__(c, Object)
    return c


def _make_room(coord=None, name="Room"):
    if coord is None:
        coord = Coord("test", 0, 0, 0)
    r = Node(coord=coord, desc="A test room.", symbol="#")
    add_object(r)
    return r


class TestLookCommand:
    """INTENT: render location or named target; honor access(view) and screenreader."""

    def test_no_args_no_location(self):
        c = _make_caller()
        c.location = None
        LookCommand().run(c, None)
        c.msg.assert_called_with("You are nowhere.")

    def test_no_args_with_location(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        c.at_look = MagicMock(return_value="(rendered)")
        LookCommand().run(c, None)
        c.msg.assert_called_with("(rendered)")

    def test_no_args_blocked_by_access(self):
        c = _make_caller()
        room = _make_room()
        room.access = MagicMock(return_value=False)
        c.location = room
        LookCommand().run(c, None)
        c.msg.assert_called_with("You can't see anything.")

    def test_target_not_found(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        c.search = MagicMock(return_value=[])
        args = MagicMock(target=["mystery"])
        LookCommand().run(c, args)
        c.msg.assert_called_with("No match found for 'mystery'.")

    def test_target_resolved_via_caller(self):
        c = _make_caller()
        target = Object.create(None, "Sword")
        c.search = MagicMock(return_value=[target])
        args = MagicMock(target=["Sword"])
        c.at_look = MagicMock(return_value="(sword)")
        LookCommand().run(c, args)
        c.at_look.assert_called_with(target)
        c.msg.assert_called_with("(sword)")

    def test_target_multiple_matches(self):
        c = _make_caller()
        c.search = MagicMock(return_value=[Object.create(None, "Sword1"), Object.create(None, "Sword2")])
        args = MagicMock(target=["Sword"])
        LookCommand().run(c, args)
        c.msg.assert_called_with("Multiple matches for 'Sword'.")


class TestEmoteCommand:
    """INTENT: broadcast `${caller.name} ${text}` to location."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        EmoteCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_location_falls_through(self):
        c = _make_caller()
        c.location = None
        args = MagicMock(text=["waves"])
        EmoteCommand().run(c, args)
        c.msg.assert_called_once()  # help

    def test_broadcasts_to_location(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        room.msg_contents = MagicMock()
        args = MagicMock(text=["waves", "happily"])
        EmoteCommand().run(c, args)
        room.msg_contents.assert_called_once()
        msg = room.msg_contents.call_args.args[0]
        assert "Alice" in msg
        assert "waves happily" in msg

    def test_alias_is_colon(self):
        assert ":" in EmoteCommand.aliases


class TestGiveCommand:
    """INTENT: move object from caller's inventory to target, with pre/post hooks."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        GiveCommand().run(c, None)
        c.msg.assert_called_once()

    def test_no_target_name_msg(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        args = MagicMock(object="apple", target=[])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("Give it to whom?")

    def test_target_not_found(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        room.search = MagicMock(return_value=[])
        args = MagicMock(object="apple", target=["bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("Could not find 'bob' here.")

    def test_cannot_give_to_self(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        # search returns the caller
        c.id = 999
        target = MagicMock()
        target.id = 999
        room.search = MagicMock(return_value=[target])
        args = MagicMock(object="apple", target=["me"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("You already have that!")

    def test_dont_have_it(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        target = Object.create(None, "Bob")
        room.search = MagicMock(return_value=[target])
        c.search = MagicMock(return_value=[])
        args = MagicMock(object="apple", target=["bob"])
        GiveCommand().run(c, args)
        c.msg.assert_called_with("You don't have that.")

    def test_successful_give(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        target = Object.create(None, "Bob")
        target.msg = MagicMock()
        room.search = MagicMock(return_value=[target])
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        # pre/post hooks default to True
        c.search = MagicMock(return_value=[apple])
        room.msg_contents = MagicMock()
        args = MagicMock(object="apple", target=["bob"])
        GiveCommand().run(c, args)
        # Apple moved
        assert apple.id in target.contents or apple in target.contents or apple.location is target
        target.msg.assert_called()
        c.msg.assert_called_with("You give Apple to Bob.")

    def test_filters_out_to_keyword(self):
        c = _make_caller()
        room = _make_room()
        c.location = room
        target = Object.create(None, "Bob")
        room.search = MagicMock(return_value=[target])
        c.search = MagicMock(return_value=[])
        args = MagicMock(object="apple", target=["to", "bob"])
        GiveCommand().run(c, args)
        # "to" filtered; bob is the target
        c.msg.assert_called_with("You don't have that.")


class TestTimeCommand:
    def test_shows_formatted_time(self):
        c = _make_caller()
        with patch("atheriz.commands.loggedin.time.get_game_time") as mock_gt:
            mock_gt.return_value.get_time.return_value = {"formatted": "12:00 PM"}
            TimeCommand().run(c, None)
        c.msg.assert_called_with("12:00 PM")


class TestReloadCommand:
    """INTENT: superuser-only; broadcasts to server channel, calls reload_game_logic."""

    def test_access_requires_superuser(self):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Player
        assert ReloadCommand().access(c) is False

    def test_access_for_superuser(self):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Admin
        assert ReloadCommand().access(c) is True

    def test_run_no_channel(self):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Admin
        with patch("atheriz.commands.loggedin.reload.get_server_channel", return_value=None), \
             patch("atheriz.commands.loggedin.reload.reload_game_logic", return_value="ok"):
            ReloadCommand().run(c, None)
        # No channel, so result went to caller.msg
        c.msg.assert_called_with("ok")

    def test_run_with_channel(self):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Admin
        channel = MagicMock()
        with patch("atheriz.commands.loggedin.reload.get_server_channel", return_value=channel), \
             patch("atheriz.commands.loggedin.reload.reload_game_logic", return_value="reloaded"):
            ReloadCommand().run(c, None)
        channel.msg.assert_any_call("Server is reloading...")
        channel.msg.assert_any_call("reloaded")


class TestShutdownCommand:
    """INTENT: superuser-only; triggers shutdown endpoint with admin token."""

    def test_access_requires_superuser(self):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Player
        assert ShutdownCommand().access(c) is False

    def test_no_token_file(self, global_test_env, tmp_path):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Admin
        with patch.object(settings, "SECRET_PATH", str(tmp_path)):
            ShutdownCommand().run(c, None)
        c.msg.assert_called_with("Error: admin.token not found.")

    def test_successful_shutdown(self, global_test_env, tmp_path):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Admin
        (tmp_path / "admin.token").write_text("test_token")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = json.dumps({"status": "ok", "message": "shutting down"}).encode()

        with patch.object(settings, "SECRET_PATH", str(tmp_path)), \
             patch("atheriz.commands.loggedin.shutdown.urllib.request.urlopen", return_value=mock_response):
            ShutdownCommand().run(c, None)
        c.msg.assert_any_call("Server shutdown initiated successfully.")

    def test_shutdown_endpoint_error(self, global_test_env, tmp_path):
        c = _make_caller()
        c.privilege_level = settings.Privilege.Admin
        (tmp_path / "admin.token").write_text("tok")
        with patch.object(settings, "SECRET_PATH", str(tmp_path)), \
             patch("atheriz.commands.loggedin.shutdown.urllib.request.urlopen",
                   side_effect=Exception("connect refused")):
            ShutdownCommand().run(c, None)
        assert any("Shutdown error" in str(c) or "Error connecting" in str(c) for c in c.msg.call_args_list)


class TestNoneCommand:
    """INTENT: command not found; suggest closest match via Levenshtein distance."""

    def test_no_args_msg(self):
        c = _make_caller()
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.commands = {"look": 1, "say": 2}
        NoneCommand().run(c, None)
        c.msg.assert_called_with("Command not found.")

    def test_suggests_closest_match(self):
        c = _make_caller()
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.commands = {"look": 1, "say": 2}
        with patch("atheriz.commands.loggedin.none.get_loggedin_cmdset") as mock_lcs:
            mock_lcs.return_value.commands = {}
            args = MagicMock(none=["lrok"])  # typo of "look"
            NoneCommand().run(c, args)
        msg = c.msg.call_args.args[0]
        assert "did you mean" in msg
        assert "look" in msg

    def test_no_choices_no_suggestion(self):
        c = _make_caller()
        c.internal_cmdset = MagicMock()
        c.internal_cmdset.commands = {}
        with patch("atheriz.commands.loggedin.none.get_loggedin_cmdset") as mock_lcs:
            mock_lcs.return_value.commands = {}
            args = MagicMock(none=["xyz"])
            NoneCommand().run(c, args)
        msg = c.msg.call_args.args[0]
        assert "not found" in msg
        assert "did you mean" not in msg
