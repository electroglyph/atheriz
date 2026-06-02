"""Tests for simple loggedin commands: desc, say, quit, inventory, quell, save."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.loggedin.desc import DescCommand
from atheriz.commands.loggedin.inventory import InventoryCommand
from atheriz.commands.loggedin.quell import QuellCommand, UnquellCommand
from atheriz.commands.loggedin.quit import QuitCommand
from atheriz.commands.loggedin.save import SaveCommand
from atheriz.commands.loggedin.say import SayCommand
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object


def _make_caller(name="Alice", builder=False, superuser=False, msg=None):
    c = Object.create(None, name)
    if superuser:
        c.privilege_level = settings.Privilege.Admin
    elif builder:
        c.privilege_level = settings.Privilege.Builder
    else:
        c.privilege_level = settings.Privilege.Player
    c.quelled = False
    c.msg = msg or MagicMock()
    return c


class TestDescCommand:
    """INTENT: builder-only command that changes current room description."""

    def test_access_requires_builder(self):
        c = _make_caller(builder=False)
        assert DescCommand().access(c) is False

    def test_access_allowed_for_builder(self):
        c = _make_caller(builder=True)
        assert DescCommand().access(c) is True

    def test_no_args_shows_help(self):
        c = _make_caller(builder=True)
        DescCommand().run(c, None)
        # Help printed to caller
        c.msg.assert_called_once()
        assert "Aliases" in c.msg.call_args.args[0] or "desc" in c.msg.call_args.args[0]

    def test_empty_text_falls_through_to_help(self):
        c = _make_caller(builder=True)
        args = MagicMock()
        args.text = None
        DescCommand().run(c, args)
        c.msg.assert_called_once()

    def test_no_location_msg_nowhere(self, global_test_env):
        c = _make_caller(builder=True)
        c.location = None
        args = MagicMock(text=["A", "new", "desc"])
        DescCommand().run(c, args)
        c.msg.assert_called_with("You are nowhere!")

    def test_sets_desc_with_newlines(self, global_test_env):
        c = _make_caller(builder=True)
        loc = MagicMock()
        loc.desc = ""
        c.location = loc
        c.at_look = MagicMock(return_value="(looked)")
        args = MagicMock(text=["Line1", "\\n", "Line2"])
        DescCommand().run(c, args)
        # \n was replaced with actual newline
        assert loc.desc == "Line1 \n Line2"
        # at_look was called to display the change
        c.msg.assert_called_with("(looked)")


class TestSayCommand:
    """INTENT: caller's at_say hook is invoked with the joined text."""

    def test_no_args_shows_help(self):
        c = _make_caller()
        SayCommand().run(c, None)
        c.msg.assert_called_once()

    def test_calls_at_say_with_joined_text(self):
        c = _make_caller()
        args = MagicMock(text=["hello", "world"])
        c.at_say = MagicMock()
        SayCommand().run(c, args)
        c.at_say.assert_called_once_with("hello world")

    def test_empty_text_shows_help(self):
        c = _make_caller()
        args = MagicMock(text=None)
        c.at_say = MagicMock()
        SayCommand().run(c, args)
        c.at_say.assert_not_called()
        c.msg.assert_called_once()

    def test_alias_is_apostrophe(self):
        assert "'" in SayCommand.aliases


class TestQuitCommand:
    """INTENT: send goodbye, then close the underlying connection."""

    def test_sends_goodbye_and_closes(self):
        c = _make_caller()
        c.session = MagicMock()
        c.session.connection = MagicMock()
        QuitCommand().run(c, None)
        c.msg.assert_called_once_with("Goodbye!")
        c.session.connection.close.assert_called_once()

    def test_aliases_include_logout(self):
        assert "logout" in QuitCommand.aliases
        assert "exit" in QuitCommand.aliases
        assert "disconnect" in QuitCommand.aliases


class TestInventoryCommand:
    """INTENT: list carried items via group_by_name; show 'carrying nothing' if empty."""

    def test_empty_inventory_msg(self):
        c = _make_caller()
        # No contents
        InventoryCommand().run(c, None)
        c.msg.assert_called_once_with("You are carrying nothing.")

    def test_lists_items(self):
        c = _make_caller()
        apple = Object.create(None, "Apple")
        apple.move_to(c)
        InventoryCommand().run(c, None)
        c.msg.assert_called_once()
        msg = c.msg.call_args.args[0]
        assert "Apple" in msg
        assert "carrying" in msg

    def test_inventory_alias_is_i(self):
        assert "i" in InventoryCommand.aliases


class TestQuellCommand:
    """INTENT: quell / unquell toggles the quelled flag on a builder."""

    def test_quell_requires_builder(self):
        c = _make_caller(builder=False)
        assert QuellCommand().access(c) is False

    def test_quell_sets_quelled(self):
        c = _make_caller(builder=True)
        c.quelled = False
        QuellCommand().run(c, None)
        assert c.quelled is True
        c.msg.assert_called_with("You are now quelled.")

    def test_quell_already_quelled_msg(self):
        c = _make_caller(builder=True)
        c.quelled = True
        QuellCommand().run(c, None)
        assert c.quelled is True
        c.msg.assert_called_with("You are already quelled!")


class TestUnquellCommand:
    def test_unquell_requires_builder(self):
        c = _make_caller(builder=False)
        assert UnquellCommand().access(c) is False

    def test_unquell_clears_quelled(self):
        c = _make_caller(builder=True)
        c.quelled = True
        UnquellCommand().run(c, None)
        assert c.quelled is False
        c.msg.assert_called_with("You are now unquelled.")

    def test_unquell_not_quelled_msg(self):
        c = _make_caller(builder=True)
        c.quelled = False
        UnquellCommand().run(c, None)
        assert c.quelled is False
        c.msg.assert_called_with("You are not quelled!")


class TestSaveCommand:
    """INTENT: superuser-only command that persists all globals."""

    def test_access_requires_superuser(self):
        c = _make_caller(builder=True, superuser=False)
        assert SaveCommand().access(c) is False

    def test_access_allowed_for_superuser(self):
        c = _make_caller(superuser=True)
        assert SaveCommand().access(c) is True

    def test_save_calls_all_handlers(self):
        c = _make_caller(superuser=True)
        with patch("atheriz.commands.loggedin.save.save_objects") as mock_save, \
             patch("atheriz.commands.loggedin.save.get_map_handler") as mock_mh, \
             patch("atheriz.commands.loggedin.save.get_node_handler") as mock_nh, \
             patch("atheriz.commands.loggedin.save.get_game_time") as mock_gt:
            mock_mh.return_value.save = MagicMock()
            mock_nh.return_value.save = MagicMock()
            mock_gt.return_value.save = MagicMock()
            SaveCommand().run(c, None)

        # All save methods called
        mock_save.assert_called_once()
        mock_mh.return_value.save.assert_called_once()
        mock_nh.return_value.save.assert_called_once()
        # Game time save depends on TIME_SYSTEM_ENABLED; default is False so not called
        assert "Saved in" in c.msg.call_args.args[0]

    def test_save_calls_game_time_when_enabled(self):
        c = _make_caller(superuser=True)
        old = settings.TIME_SYSTEM_ENABLED
        settings.TIME_SYSTEM_ENABLED = True
        try:
            with patch("atheriz.commands.loggedin.save.save_objects"), \
                 patch("atheriz.commands.loggedin.save.get_map_handler") as mock_mh, \
                 patch("atheriz.commands.loggedin.save.get_node_handler") as mock_nh, \
                 patch("atheriz.commands.loggedin.save.get_game_time") as mock_gt:
                mock_mh.return_value.save = MagicMock()
                mock_nh.return_value.save = MagicMock()
                mock_gt.return_value.save = MagicMock()
                SaveCommand().run(c, None)
            mock_gt.return_value.save.assert_called_once()
        finally:
            settings.TIME_SYSTEM_ENABLED = old
