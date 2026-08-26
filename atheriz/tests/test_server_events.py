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
        existing = Account.create("alice", "password123")
        assert existing is not None

        with patch("atheriz.server_events.save_objects") as mock_save, \
             patch("atheriz.server_events.Object.create") as mock_create:
            at_char_create("alice", "Bob", "wrongpass123")

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
        existing = Account.create("alice", "password123")
        # Fill to max
        existing.characters = list(range(settings.MAX_CHARACTERS))

        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Object.create") as mock_create:
            at_char_create("alice", "Bob", "password123")

        mock_create.assert_not_called()
        captured = capsys.readouterr()
        assert "already has" in captured.out


class TestAtCharCreateExistingAccount:
    """INTENT: existing account + correct password = new character added to account."""

    def test_creates_character_under_existing(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import get
        existing = Account.create("alice", "password123")
        initial_count = len(existing.characters)

        with patch("atheriz.server_events.save_objects") as mock_save, \
             patch("atheriz.server_events.Object.create", wraps=Object.create):
            at_char_create("alice", "Bob", "password123")

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
        existing = Account.create("alice", "password123")

        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Object.create", wraps=Object.create):
            at_char_create("alice", "Bob", "password123")

        new_char = get(existing.characters[-1])[0]
        # home (the Node) is stored on the character
        assert new_char.home is real_home_node

    def test_calls_move_to_with_home(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        existing = Account.create("alice", "password123")

        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Object.create", wraps=Object.create), \
             patch("atheriz.objects.base_obj.Object.move_to") as mock_move:
            at_char_create("alice", "Bob", "password123")

        # move_to was called once with the home node
        mock_move.assert_called_once()
        assert mock_move.call_args.args[0] is real_home_node


class TestAtCharCreateNewAccount:
    """INTENT: new account = Account.create + new character + both added to global objects."""

    def test_creates_account_when_none_exists(self, global_test_env, real_home_node, fixed_salt):
        with patch("atheriz.server_events.save_objects") as mock_save, \
             patch("atheriz.objects.base_obj.Object.move_to"):
            at_char_create("newuser", "Newbie", "password123")

        from atheriz.globals.objects import filter_by

        assert len(filter_by(lambda x: getattr(x, "is_account", False) and x.name == "newuser")) == 1
        assert len(filter_by(lambda x: getattr(x, "is_pc", False) and x.name == "Newbie")) >= 1
        mock_save.assert_called_once()

    def test_returns_early_when_account_create_fails(self, global_test_env, real_home_node):
        # INTENT: if Account.create returns None (e.g., duplicate race), early return
        with patch("atheriz.server_events.Account.create", return_value=None), \
              patch("atheriz.server_events.save_objects") as mock_save:
            at_char_create("dup", "X", "pw")

        mock_save.assert_not_called()


class TestAtCharCreatePersistence:
    def test_existing_account_new_character_marks_account_modified(self, global_test_env, real_home_node, fixed_salt, monkeypatch):
        import atheriz.settings as settings
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import save_objects, load_objects, get as gl_get
        import dill
        from atheriz import database_setup

        monkeypatch.setattr(settings, "ALWAYS_SAVE_ALL", False)
        account = Account.create("persist_acct", "password123")
        from atheriz.globals.objects import _ALL_OBJECTS
        save_objects()
        object.__setattr__(account, "is_modified", False)
        assert account.is_modified is False
        at_char_create("persist_acct", "NewHero", "password123")
        assert account.is_modified is True
        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM objects WHERE id=?", (account.id,))
            row = cur.fetchone()
            assert row is not None
            loaded = dill.loads(row[0])
            assert any(
                gl_get(cid) and gl_get(cid)[0].name == "NewHero" for cid in loaded.characters
            ) or loaded.characters == account.characters
            assert len(loaded.characters) >= 1 and loaded.characters[-1] in [c for c in loaded.characters]

    def test_existing_account_second_character_persists_across_reload(self, global_test_env, real_home_node, fixed_salt, monkeypatch):
        import atheriz.settings as settings
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import save_objects, load_objects, _ALL_OBJECTS
        from atheriz import database_setup
        import dill
        monkeypatch.setattr(settings, "ALWAYS_SAVE_ALL", False)
        account = Account.create("reload_acct", "password123")
        save_objects()
        object.__setattr__(account, "is_modified", False)
        at_char_create("reload_acct", "SecondHero", "password123")
        save_objects()
        saved_chars = list(account.characters)
        assert len(saved_chars) >= 1
        _ALL_OBJECTS.clear()
        database_setup.get_database().close()
        database_setup.reopen_database()
        database_setup.do_setup()
        load_objects()
        from atheriz.globals.objects import filter_by

        reloaded = filter_by(lambda x: getattr(x, "is_account", False) and x.name == "reload_acct")
        assert reloaded
        assert reloaded[0].characters == saved_chars

    def test_cli_character_name_uniqueness_enforced(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import filter_by

        Account.create("uniq_acct1", "password123")
        Account.create("uniq_acct2", "password123")
        at_char_create("uniq_acct1", "HeroDup", "password123")
        at_char_create("uniq_acct2", "herodup", "password123")
        heroes = filter_by(lambda x: getattr(x, "is_pc", False) and x.name.lower() == "herodup")
        assert len(heroes) == 1

    def test_cli_character_name_validation_rejects_invalid(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.globals.objects import filter_by

        at_char_create("badname_acct", "x", "password123")
        pcs = filter_by(lambda x: getattr(x, "is_pc", False) and x.name == "x")
        assert pcs == []


class TestAtCharCreateWeakPassword:
    def test_cli_weak_password_rejected(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.globals.objects import filter_by
        at_char_create("weak_acct", "HeroWeak", "x")
        accts = filter_by(lambda x: getattr(x, "is_account", False) and x.name == "weak_acct")
        assert accts == [], "CLI must validate password, short 'x' should not create account"
        pcs = filter_by(lambda x: getattr(x, "is_pc", False) and x.name == "HeroWeak")
        assert pcs == []

    def test_cli_short_password_does_not_create_account(self, global_test_env, real_home_node):
        from atheriz.globals.objects import filter_by
        from unittest.mock import patch
        with patch("atheriz.server_events.save_objects"):
            at_char_create("shortpwacct", "HeroShort", "short")
            accts = filter_by(lambda x: getattr(x, "is_account", False) and x.name == "shortpwacct")
            assert accts == [], "password shorter than MIN_PASSWORD_LENGTH must be rejected"

    def test_cli_password_validation_enforced_on_existing_account(self, global_test_env, real_home_node, fixed_salt):
        from atheriz.objects.base_account import Account
        from atheriz.globals.objects import filter_by
        Account.create("existacct", "validpass123")
        from unittest.mock import patch
        with patch("atheriz.server_events.save_objects"):
            at_char_create("existacct", "NewHero2", "x")
            heroes = filter_by(lambda x: getattr(x, "is_pc", False) and x.name == "NewHero2")
            assert heroes == [], "even for existing account, weak char name or short pw should not create"


class TestPasswordPolicy:
    def test_validation_rejects_short_password(self):
        from atheriz.commands.unloggedin.validation import validate_password
        assert validate_password("x") is not None
        assert validate_password("") is not None
        assert validate_password("short") is not None

    def test_cli_at_char_create_calls_validate_password(self, global_test_env, real_home_node):
        from unittest.mock import patch
        with patch("atheriz.server_events.save_objects"), \
             patch("atheriz.server_events.Account.create") as mock_create, \
             patch("atheriz.server_events.Object.create") as mock_obj:
            at_char_create("anyacct", "AnyHero", "x")
            assert mock_create.called is False, "short password must not reach Account.create"
            assert mock_obj.called is False

    def test_min_password_length_not_weak(self):
        import atheriz.settings as s
        assert s.MIN_PASSWORD_LENGTH >= 8, "MIN_PASSWORD_LENGTH must be at least 8"
        from atheriz.commands.unloggedin.validation import validate_password
        assert validate_password("1234567") is not None
        assert validate_password("12345678") is None or "at least" not in validate_password("12345678")
