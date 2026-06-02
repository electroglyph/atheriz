"""Tests for unloggedin commands: connect, guest, screenreader, quit."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.unloggedin.connect import ConnectCommand
from atheriz.commands.unloggedin.guest import GuestCommand
from atheriz.commands.unloggedin.quit import QuitCommand
from atheriz.commands.unloggedin.screenreader import ScreenReaderCommand
from atheriz.globals.objects import add_object
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object


class TestScreenReaderCommand:
    """INTENT: toggle screenreader mode; send 'screenreader' command to client."""

    def test_toggle_off_to_on(self):
        caller = MagicMock()
        caller.session.screenreader = False
        caller.session.connection = MagicMock()
        ScreenReaderCommand().run(caller, None)
        assert caller.session.screenreader is True
        caller.session.connection.send_command.assert_called_once_with("screenreader", True)

    def test_toggle_on_to_off(self):
        caller = MagicMock()
        caller.session.screenreader = True
        caller.session.connection = MagicMock()
        ScreenReaderCommand().run(caller, None)
        assert caller.session.screenreader is False
        caller.session.connection.send_command.assert_called_once_with("screenreader", False)

    def test_alias_is_sr(self):
        assert "sr" in ScreenReaderCommand.aliases


class TestUnloggedinQuit:
    def test_sends_goodbye_and_closes(self):
        c = MagicMock()
        c.session.connection = MagicMock()
        QuitCommand().run(c, None)
        c.msg.assert_called_once_with("Goodbye!")
        c.session.connection.close.assert_called_once()

    def test_aliases(self):
        assert "exit" in QuitCommand.aliases
        assert "logout" in QuitCommand.aliases
        assert "disconnect" in QuitCommand.aliases


class TestConnectCommand:
    """INTENT: validate credentials, puppet character, manage failed login attempts."""

    def _make_caller(self, name="alice", pw="secret"):
        """Create a connection-like caller with msg, session, send_command."""
        caller = MagicMock()
        caller.session = MagicMock()
        caller.session.account = None
        caller.session.puppet = None
        caller.msg = MagicMock()
        caller.send_command = MagicMock()
        caller.failed_login_attempts = 0
        caller.client_host = "1.2.3.4"
        return caller

    def _run(self, cmd, *args):
        return cmd.run(*args)

    def test_account_not_found_msg_invalid_password(self, global_test_env, fixed_salt):
        # INTENT: no enumeration - say "Invalid password" not "not found"
        caller = self._make_caller()
        parsed = MagicMock(account_name="nobody", password="pw")
        asyncio.run(self._run(ConnectCommand(), caller, parsed))
        caller.msg.assert_called_with("Invalid password.")

    def test_wrong_password_increments_attempts(self, global_test_env, fixed_salt):
        Account.create("alice", "correct")
        caller = self._make_caller()
        parsed = MagicMock(account_name="alice", password="wrong")
        asyncio.run(self._run(ConnectCommand(), caller, parsed))
        assert caller.failed_login_attempts == 1
        caller.msg.assert_called_with("Invalid password.")

    def test_too_many_failures_bans_ip(self, global_test_env, fixed_salt):
        from atheriz.globals.objects import TEMP_BANNED_IPS
        Account.create("alice", "correct")
        caller = self._make_caller()
        caller.failed_login_attempts = settings.MAX_LOGIN_ATTEMPTS + 1
        parsed = MagicMock(account_name="alice", password="wrong")
        asyncio.run(self._run(ConnectCommand(), caller, parsed))
        # Banned
        assert caller.client_host in TEMP_BANNED_IPS
        caller.close.assert_called_once()
        assert any("Too many" in str(call) for call in caller.msg.call_args_list)

    def test_correct_password_with_none_characters_msg(self, global_test_env, fixed_salt):
        # INTENT: characters=None is the "creation not implemented" path
        acc = Account.create("alice", "correct")
        acc.characters = None
        caller = self._make_caller()
        parsed = MagicMock(account_name="alice", password="correct")
        asyncio.run(self._run(ConnectCommand(), caller, parsed))
        # 'logged_in' still sent
        caller.send_command.assert_called_with("logged_in")
        # But "not implemented" message
        assert any("not implemented" in str(c) for c in caller.msg.call_args_list)

    def test_banned_account_closed(self, global_test_env, fixed_salt):
        acc = Account.create("alice", "correct")
        acc.is_banned = True
        acc.ban_reason = "spam"
        caller = self._make_caller()
        parsed = MagicMock(account_name="alice", password="correct")
        asyncio.run(self._run(ConnectCommand(), caller, parsed))
        caller.close.assert_called_once()
        assert any("banned" in str(c) for c in caller.msg.call_args_list)


class TestGuestCommand:
    """INTENT: create temporary PC and puppet them at DEFAULT_HOME."""

    def _make_caller(self):
        caller = MagicMock()
        caller.session = MagicMock()
        caller.session.puppet = None
        caller.msg = MagicMock()
        caller.send_command = MagicMock()
        return caller

    def test_disabled_msg(self, global_test_env):
        old = settings.GUEST_ENABLED
        settings.GUEST_ENABLED = False
        try:
            caller = self._make_caller()
            asyncio.run(GuestCommand().run(caller, None))
            caller.msg.assert_called_with("Guest accounts are not enabled.")
        finally:
            settings.GUEST_ENABLED = old

    def test_empty_name_msg(self, global_test_env):
        old = settings.GUEST_ENABLED
        settings.GUEST_ENABLED = True
        try:
            caller = self._make_caller()
            caller.session.prompt = AsyncMock(side_effect=["", "", ""])
            asyncio.run(GuestCommand().run(caller, None))
            assert any("empty" in str(c) for c in caller.msg.call_args_list)
        finally:
            settings.GUEST_ENABLED = old

    def test_creates_temporary_character(self, global_test_env):
        old_enabled = settings.GUEST_ENABLED
        old_home = settings.DEFAULT_HOME
        settings.GUEST_ENABLED = True
        from atheriz.objects.nodes import Node, Coord
        from atheriz.globals.objects import add_object
        from atheriz.globals.get import get_unique_id, get_node_handler
        home_coord = Coord("limbo", 0, 0, 0)
        home = Node(coord=home_coord, desc="Home", symbol="#")
        home.id = get_unique_id()
        add_object(home)
        nh = get_node_handler()
        # Patch nh.get_node to return our home
        nh.get_node = MagicMock(return_value=home)
        try:
            caller = self._make_caller()
            # name -> M -> desc
            caller.session.prompt = AsyncMock(side_effect=["Guest1", "M", "A wanderer"])
            asyncio.run(GuestCommand().run(caller, None))
            # Character created and puppetted
            assert caller.session.puppet is not None
            assert caller.session.puppet.is_temporary is True
            assert caller.session.puppet.is_pc is True
            assert caller.session.puppet.gender == "Male"
        finally:
            settings.GUEST_ENABLED = old_enabled
            settings.DEFAULT_HOME = old_home
