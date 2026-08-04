"""Issue tests: Account.remove_character raises ValueError when the character
isn't in the list, and login() leaves `logged_in` set after a failed login.
"""
from __future__ import annotations

import pytest

from atheriz.globals.objects import add_object
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object


class TestAccountCharacters:
    def test_remove_missing_character_is_noop(self, global_test_env, fixed_salt):
        """INTENT: removing a character that was never added must be a no-op,
        not raise ValueError from list.remove."""
        account = Account.create("bob", "pw1")
        other = Object.create(None, "other")
        add_object(other)
        account.remove_character(other)

    def test_remove_added_character_works(self, global_test_env, fixed_salt):
        account = Account.create("bob", "pw1")
        char = Object.create(None, "hero", is_pc=True)
        add_object(char)
        account.add_character(char)
        account.remove_character(char)
        assert char.id not in account.characters


class TestAccountLogin:
    def test_failed_login_clears_logged_in(self, global_test_env, fixed_salt):
        """INTENT: after a successful login, a subsequent failed login must not
        leave the account marked as logged in."""
        account = Account.create("bob", "pw1")
        assert account.login("bob", "pw1") is True
        assert account.logged_in is True

        assert account.login("bob", "wrong") is False
        assert account.logged_in is False
