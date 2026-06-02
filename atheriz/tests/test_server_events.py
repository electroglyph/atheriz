"""Tests for atheriz.server_events — server lifecycle hooks and at_char_create."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atheriz.objects.base_obj import Object
from atheriz.server_events import (
    at_char_create,
    at_server_reload,
    at_server_start,
    at_server_stop,
)


class TestLifecycleHooks:
    """INTENT: at_server_start/stop/reload are no-op extension points for game code."""

    def test_at_server_start_is_noop(self):
        # INTENT: hook is callable and returns nothing (None)
        assert at_server_start() is None

    def test_at_server_stop_is_noop(self):
        assert at_server_stop() is None

    def test_at_server_reload_is_noop(self):
        assert at_server_reload() is None


@pytest.fixture
def real_home_node():
    """Create a real Node and patch get_node_handler to return it as the home."""
    from atheriz.objects.nodes import Node, Coord
    from atheriz.globals.objects import add_object
    from atheriz.globals.get import get_unique_id

    home_coord = Coord("limbo", 0, 0, 0)
    home = Node(coord=home_coord, desc="Home", theme="limbo", symbol="#")
    home.id = get_unique_id()
    add_object(home)

    nh = MagicMock()
    nh.get_node.return_value = home
    with patch("atheriz.server_events.get_node_handler", return_value=nh):
        yield home


class TestAtCharCreateWrongPassword:
    """INTENT: existing account with wrong password = early return, no character."""

    def test_returns_early_no_new_character(self, global_test_env, real_home_node, capsys):
        from atheriz.objects.base_account import Account
        existing = Account.create("alice", "secret")
        assert existing is not None

        with patch("atheriz.server_events.save_objects") as mock_save, \
             patch("atheriz.server_events.Object.create") as mock_create:
            at_char_create("alice", "Bob", "wrongpw")

        # No new character was created
        mock_create.assert_not_called()
        mock_save.assert_not_called()
        captured = capsys.readouterr()
        assert "different password" in captured.out


class TestAtCharCreateMaxCharacters:
    """INTENT: at MAX_CHARACTERS, no new character is created."""

    def test_returns_early_when_max(self, global_test_env, real_home_node, capsys, fixed_salt):
        from atheriz.objects.base_account import Account
        from atheriz import settings
        existing = Account.create("alice", "secret")
        # Fill to max
        existing.characters = list(range(settings.MAX_CHARACTERS))

        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Object.create") as mock_create:
            at_char_create("alice", "Bob", "secret")

        mock_create.assert_not_called()
        captured = capsys.readouterr()
        assert "already has" in captured.out


class TestAtCharCreateExistingAccount:
    """INTENT: existing account + correct password = new character added to account."""

    def test_creates_character_under_existing(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import get
        existing = Account.create("alice", "secret")
        initial_count = len(existing.characters)

        with patch("atheriz.server_events.save_objects") as mock_save, \
             patch("atheriz.server_events.Object.create", wraps=Object.create):
            at_char_create("alice", "Bob", "secret")

        # Account now has one more character
        assert len(existing.characters) == initial_count + 1
        # Saved
        mock_save.assert_called_once()
        # New character is a pc
        new_char = get(existing.characters[-1])[0]
        assert new_char.is_pc is True
        assert new_char.name == "Bob"

    def test_sets_home(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import get
        existing = Account.create("alice", "secret")

        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Object.create", wraps=Object.create):
            at_char_create("alice", "Bob", "secret")

        new_char = get(existing.characters[-1])[0]
        # home (the Node) is stored on the character
        assert new_char.home is real_home_node

    def test_calls_move_to_with_home(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        existing = Account.create("alice", "secret")

        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Object.create", wraps=Object.create), \
             patch("atheriz.objects.base_obj.Object.move_to") as mock_move:
            at_char_create("alice", "Bob", "secret")

        # move_to was called once with the home node
        mock_move.assert_called_once()
        assert mock_move.call_args.args[0] is real_home_node


class TestAtCharCreateNewAccount:
    """INTENT: new account = Account.create + new character + both added to global objects."""

    def test_creates_account_when_none_exists(self, global_test_env, real_home_node, fixed_salt):
        with patch("atheriz.server_events.save_objects") as mock_save, \
             patch("atheriz.server_events.add_object") as mock_add, \
             patch("atheriz.objects.base_obj.Object.move_to"):
            at_char_create("newuser", "Newbie", "pw")

        # Account.create + Object.create = at least 2 add_object calls
        assert mock_add.call_count >= 2
        mock_save.assert_called_once()

    def test_returns_early_when_account_create_fails(self, global_test_env, real_home_node):
        # INTENT: if Account.create returns None (e.g., duplicate race), early return
        with patch("atheriz.server_events.Account.create", return_value=None), \
             patch("atheriz.server_events.save_objects") as mock_save:
            at_char_create("dup", "X", "pw")

        mock_save.assert_not_called()
