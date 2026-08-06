"""Tests for unloggedin commands: connect, guest, create, new, screenreader, quit."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atheriz import settings
from atheriz.commands.unloggedin.connect import ConnectCommand, char_selection
from atheriz.commands.unloggedin.create import CreateCommand
from atheriz.commands.unloggedin.guest import GuestCommand
from atheriz.commands.unloggedin.new import NewCharacterCommand
from atheriz.globals.objects import CREATION_COOLDOWNS
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

    def test_banned_account_closed(self, global_test_env, fixed_salt):
        acc = Account.create("alice", "correct")
        acc.is_banned = True
        acc.ban_reason = "spam"
        caller = self._make_caller()
        parsed = MagicMock(account_name="alice", password="correct")
        asyncio.run(self._run(ConnectCommand(), caller, parsed))
        caller.close.assert_called_once()
        assert any("banned" in str(c) for c in caller.msg.call_args_list)


class TestCharSelection:
    """INTENT: the post-login screen lets a user pick an existing character,
    or type 'new' (when char creation is enabled) to create one."""

    def _make_caller(self):
        caller = MagicMock()
        caller.session = MagicMock()
        caller.session.account = None
        caller.session.puppet = None
        caller.msg = MagicMock()
        return caller

    def _make_account_with_char(self):
        account = Account.create("alice", "secret")
        char = Object.create(None, "Hob", is_pc=True)
        account.add_character(char)
        return account, char

    def test_has_char_false_without_creation(self, global_test_env, fixed_salt):
        # INTENT: char creation disabled + no chars -> "no characters to play"
        old = settings.CHAR_CREATION_ENABLED
        settings.CHAR_CREATION_ENABLED = False
        try:
            account = Account.create("alice", "secret")
            caller = self._make_caller()
            caller.session.account = account
            caller.session.prompt = AsyncMock(return_value="0")
            asyncio.run(char_selection(caller, account))
            assert any("no characters" in str(c) for c in caller.msg.call_args_list)
            assert caller.session.puppet is None
        finally:
            settings.CHAR_CREATION_ENABLED = old

    def test_hint_with_chars_enabled(self, global_test_env, fixed_salt):
        account, char = self._make_account_with_char()
        caller = self._make_caller()
        caller.session.account = account
        caller.session.prompt = AsyncMock(return_value="0")
        asyncio.run(char_selection(caller, account))
        assert caller.session.puppet is char
        assert any("or type 'new'" in str(c) for c in caller.msg.call_args_list)

    def test_hint_without_chars_enabled(self, global_test_env, fixed_salt):
        account = Account.create("alice", "secret")
        caller = self._make_caller()
        caller.session.account = account

        async def fake_new_run(caller, args):
            caller.session.puppet = MagicMock()

        with patch("atheriz.commands.unloggedin.new.NewCharacterCommand") as New:
            New.return_value.run = fake_new_run
            caller.session.prompt = AsyncMock(return_value="new")
            asyncio.run(char_selection(caller, account))
        # The new command was invoked; it is responsible for setting the puppet.
        assert caller.session.puppet is not None
        assert any("type 'new'" in str(c) for c in caller.msg.call_args_list)


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
            # Character created and puppeted
            assert caller.session.puppet is not None
            assert caller.session.puppet.is_temporary is True
            assert caller.session.puppet.is_pc is True
            assert caller.session.puppet.gender == "Male"
        finally:
            settings.GUEST_ENABLED = old_enabled
            settings.DEFAULT_HOME = old_home

    def test_rate_limits_successful_creation_per_host(self, global_test_env):
        old_enabled = settings.GUEST_ENABLED
        old_cooldown = settings.CREATION_COOLDOWN
        settings.GUEST_ENABLED = True
        settings.CREATION_COOLDOWN = 60
        CREATION_COOLDOWNS.clear()
        try:
            caller = self._make_caller()
            caller.client_host = "198.51.100.10"
            caller.session.prompt = AsyncMock(side_effect=["Guest1", "M", "A wanderer"])
            character = MagicMock()
            with patch("atheriz.commands.unloggedin.guest.Object.create", return_value=character), \
                 patch("atheriz.commands.unloggedin.guest.get_node_handler") as get_nh:
                get_nh.return_value.get_node.return_value = None
                asyncio.run(GuestCommand().run(caller, None))
                caller.session.prompt.reset_mock()
                asyncio.run(GuestCommand().run(caller, None))
            caller.session.prompt.assert_not_awaited()
            caller.msg.assert_called_with(
                "Creation is temporarily rate-limited. Please try again later."
            )
        finally:
            CREATION_COOLDOWNS.clear()
            settings.GUEST_ENABLED = old_enabled
            settings.CREATION_COOLDOWN = old_cooldown

    def test_missing_gender_reports_error_without_creation(self, global_test_env):
        old_enabled = settings.GUEST_ENABLED
        settings.GUEST_ENABLED = True
        try:
            caller = self._make_caller()
            caller.session.prompt = AsyncMock(return_value="Guest1")
            engine = MagicMock()
            engine.current_node = None
            engine.context.state = {}
            with patch("atheriz.commands.unloggedin.guest.MenuEngine", return_value=engine), \
                 patch("atheriz.commands.unloggedin.guest.Object.create") as create:
                asyncio.run(GuestCommand().run(caller, None))
            caller.msg.assert_called_with("Gender selection is required.")
            create.assert_not_called()
        finally:
            settings.GUEST_ENABLED = old_enabled


class TestCreateAccountCommand:
    """INTENT: create an account from the login screen, auto-login, drop into char selection."""

    def _make_caller(self):
        caller = MagicMock()
        caller.session = MagicMock()
        caller.session.account = None
        caller.session.prompt = AsyncMock()
        caller.msg = MagicMock()
        caller.send_command = MagicMock()
        return caller

    def test_disabled_msg(self, global_test_env):
        olds, oldc = settings.ACCOUNT_CREATION_ENABLED, settings.CHAR_CREATION_ENABLED
        settings.ACCOUNT_CREATION_ENABLED = False
        settings.CHAR_CREATION_ENABLED = True
        try:
            caller = self._make_caller()
            asyncio.run(CreateCommand().run(caller, None))
            caller.msg.assert_called_with("Account creation is not enabled.")
        finally:
            settings.ACCOUNT_CREATION_ENABLED = olds
            settings.CHAR_CREATION_ENABLED = oldc

    def test_duplicate_account(self, global_test_env, fixed_salt):
        Account.create("alice", "secret")
        caller = self._make_caller()
        caller.session.prompt = AsyncMock(side_effect=["alice", "pw"])
        asyncio.run(CreateCommand().run(caller, None))
        # ValueError caught -> error message, no new account
        caller.msg.assert_called_once()
        assert any("already exists" in str(c) for c in caller.msg.call_args_list)
        accounts = [x for x in __import__("atheriz.globals.objects", fromlist=["filter_by"]).filter_by(lambda o: o.is_account)]
        assert len(accounts) == 1

    def test_creates_and_auto_logs_in(self, global_test_env, fixed_salt):
        oldc = settings.CHAR_CREATION_ENABLED
        settings.CHAR_CREATION_ENABLED = True
        try:
            caller = self._make_caller()
            caller.session.prompt = AsyncMock(side_effect=["bob", "hunter2"])
            with patch("atheriz.commands.unloggedin.create.char_selection", new=AsyncMock()) as sel:
                asyncio.run(CreateCommand().run(caller, None))
            # auto-login
            assert caller.session.account is not None
            caller.send_command.assert_called_with("logged_in")
            sel.assert_awaited_once()
        finally:
            settings.CHAR_CREATION_ENABLED = oldc

    def test_missing_password(self, global_test_env, fixed_salt):
        caller = self._make_caller()
        caller.session.prompt = AsyncMock(side_effect=["alice", ""])
        with patch("atheriz.commands.unloggedin.create.char_selection", new=AsyncMock()) as sel:
            asyncio.run(CreateCommand().run(caller, None))
        caller.msg.assert_called_with("Password cannot be empty.")
        sel.assert_not_awaited()

    def test_rate_limits_successful_creation_per_host(self, global_test_env, fixed_salt):
        oldc = settings.ACCOUNT_CREATION_ENABLED
        old_cooldown = settings.CREATION_COOLDOWN
        settings.ACCOUNT_CREATION_ENABLED = True
        settings.CREATION_COOLDOWN = 60
        CREATION_COOLDOWNS.clear()
        try:
            caller = self._make_caller()
            caller.client_host = "198.51.100.10"
            caller.session.prompt = AsyncMock(side_effect=["bob", "hunter2"])
            with patch("atheriz.commands.unloggedin.create.Account.create") as account, \
                 patch("atheriz.commands.unloggedin.create.char_selection", new=AsyncMock()):
                asyncio.run(CreateCommand().run(caller, None))
                caller.session.prompt.reset_mock()
                asyncio.run(CreateCommand().run(caller, None))
            caller.session.prompt.assert_not_awaited()
            caller.msg.assert_called_with(
                "Creation is temporarily rate-limited. Please try again later."
            )
        finally:
            CREATION_COOLDOWNS.clear()
            settings.ACCOUNT_CREATION_ENABLED = oldc
            settings.CREATION_COOLDOWN = old_cooldown


class TestNewCharacterCommand:
    """INTENT: new creates a persistent (non-temp) character for the account and puppets it."""

    def _make_caller(self):
        caller = MagicMock()
        caller.session = MagicMock()
        caller.session.account = None
        caller.session.puppet = None
        caller.msg = MagicMock()
        return caller

    def test_disabled_msg(self, global_test_env):
        old = settings.CHAR_CREATION_ENABLED
        settings.CHAR_CREATION_ENABLED = False
        try:
            caller = self._make_caller()
            asyncio.run(NewCharacterCommand().run(caller, None))
            caller.msg.assert_called_with("Character creation is not enabled.")
        finally:
            settings.CHAR_CREATION_ENABLED = old

    def test_requires_login(self, global_test_env):
        old = settings.CHAR_CREATION_ENABLED
        settings.CHAR_CREATION_ENABLED = True
        try:
            caller = self._make_caller()
            caller.session.account = None
            asyncio.run(NewCharacterCommand().run(caller, None))
            caller.msg.assert_called_with("You must be logged in first.")
        finally:
            settings.CHAR_CREATION_ENABLED = old

    def test_max_characters(self, global_test_env, fixed_salt):
        old = settings.CHAR_CREATION_ENABLED
        old_max = settings.MAX_CHARACTERS
        settings.CHAR_CREATION_ENABLED = True
        settings.MAX_CHARACTERS = 1
        try:
            account = Account.create("alice", "secret")
            char = Object.create(None, "Full", is_pc=True)
            account.add_character(char)
            caller = self._make_caller()
            caller.session.account = account
            with patch("atheriz.commands.unloggedin.new.Object.create") as create:
                asyncio.run(NewCharacterCommand().run(caller, None))
            caller.msg.assert_called_with("You already have 1 characters.")
            create.assert_not_called()
        finally:
            settings.CHAR_CREATION_ENABLED = old
            settings.MAX_CHARACTERS = old_max

    def test_creates_persistent_character(self, global_test_env, fixed_salt):
        old = settings.CHAR_CREATION_ENABLED
        settings.CHAR_CREATION_ENABLED = True
        try:
            account = Account.create("alice", "secret")
            caller = self._make_caller()
            caller.session.account = account
            caller.session.prompt = AsyncMock(side_effect=["Hobbis", "M", "A wanderer"])
            with patch("atheriz.commands.unloggedin.new.get_node_handler") as nh:
                nh.return_value.get_node.return_value = None
                asyncio.run(NewCharacterCommand().run(caller, None))
            char = caller.session.puppet
            assert char is not None
            assert char.is_pc is True
            assert char.is_temporary is False
            assert char.gender == "Male"
            # the character is attached to the account and persisted via is_modified
            assert account.characters == [char.id]
            assert char.is_modified is True
        finally:
            settings.CHAR_CREATION_ENABLED = old

    def test_rate_limits_successful_creation_per_host(self, global_test_env, fixed_salt):
        old = settings.CHAR_CREATION_ENABLED
        old_cooldown = settings.CREATION_COOLDOWN
        settings.CHAR_CREATION_ENABLED = True
        settings.CREATION_COOLDOWN = 60
        CREATION_COOLDOWNS.clear()
        try:
            account = Account.create("alice", "secret")
            caller = self._make_caller()
            caller.client_host = "198.51.100.10"
            caller.session.account = account
            caller.session.prompt = AsyncMock(side_effect=["Hobbis", "M", "A wanderer"])
            with patch("atheriz.commands.unloggedin.new.get_node_handler") as nh:
                nh.return_value.get_node.return_value = None
                asyncio.run(NewCharacterCommand().run(caller, None))
                caller.session.prompt.reset_mock()
                asyncio.run(NewCharacterCommand().run(caller, None))
            caller.session.prompt.assert_not_awaited()
            caller.msg.assert_called_with(
                "Creation is temporarily rate-limited. Please try again later."
            )
        finally:
            CREATION_COOLDOWNS.clear()
            settings.CHAR_CREATION_ENABLED = old
            settings.CREATION_COOLDOWN = old_cooldown