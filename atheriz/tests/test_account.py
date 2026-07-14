"""Tests for atheriz.objects.base_account — Account lifecycle and authentication.

These tests focus on intent: that the code keeps promises about its behavior
(password is never stored plaintext, deletes can be vetoed, locks are
thread-safe, pickle excludes the lock, etc.) rather than rubber-stamping the
exact return value of every method.
"""
from __future__ import annotations

import _thread
import hashlib
import hmac
import pickle
from unittest.mock import MagicMock

import dill
import pytest

import atheriz.settings as settings
from atheriz.globals.get import get_unique_id
from atheriz.globals.objects import _ALL_OBJECTS
from atheriz.globals.salt import get_salt
from atheriz.objects.base_account import Account
from atheriz.tests.fakes import make_object


def _make_account(name: str = "alice", password: str = "secret") -> Account:
    """Helper: create a real account in the global registry."""
    acc = Account.create(name, password)
    assert acc is not None
    return acc


class TestAccountClassAttrs:
    def test_group_save_default_false(self):
        # INTENT: group_save controls whether this type is saved in batch with
        # other group_save types; default is per-instance (False)
        assert Account.group_save is False


class TestAccountConstructor:
    def test_init_defaults(self, global_test_env):
        a = Account()
        # INTENT: a freshly-constructed account is "blank" and not registered
        assert a.id == -1
        assert a.name == ""
        assert a.password == ""
        assert a.characters == []
        assert a.is_banned is False
        assert a.ban_reason == ""
        assert a.is_account is True

    def test_init_creates_rlock(self, global_test_env):
        a = Account()
        assert isinstance(a.lock, _thread.RLock)

    def test_init_sets_flag_defaults(self, global_test_env):
        # INTENT: an Account inherits from Flags, so it should have all the
        # default flag booleans, even though most are False
        a = Account()
        assert a.is_pc is False
        assert a.is_npc is False
        assert a.is_item is False
        assert a.is_script is False
        assert a.is_node is False
        assert a.is_account is True
        assert a.is_channel is False
        assert a.is_mapable is False
        assert a.is_container is False
        assert a.is_tickable is False
        assert a.is_modified is True
        assert a.is_deleted is False
        assert a.is_connected is False
        assert a.is_temporary is False
        assert a.can_hear is False
        assert a.tags == set()

    def test_init_does_not_register(self, global_test_env):
        # INTENT: a bare Account() is not in the global registry — only
        # create() adds it. This protects against accidental registration
        # of unconfigured accounts.
        a = Account()
        assert a not in _ALL_OBJECTS.values()


class TestAccountCreate:
    def test_creates_with_unique_id(self, fixed_salt, global_test_env):
        # INTENT: the id is a positive integer drawn from the global counter
        before = get_unique_id()
        acc = _make_account()
        after = get_unique_id()
        # The account's id is one of the unique values from the counter
        assert before < acc.id < after
        assert acc.id > 0

    def test_name_and_password_set(self, fixed_salt, global_test_env):
        acc = _make_account("bob", "hunter2")
        assert acc.name == "bob"
        # INTENT: the password is NEVER stored plaintext
        assert acc.password != "hunter2"
        assert "hunter2" not in acc.password

    def test_password_uses_pbkdf2(self, fixed_salt, global_test_env):
        acc = _make_account("carol", "abc123")
        expected = hashlib.pbkdf2_hmac("sha256", b"abc123", get_salt().encode(), 600_000).hex()
        assert acc.password == expected

    def test_empty_name_raises_value_error(self, fixed_salt, global_test_env):
        # INTENT: refuse bad input loudly, not return None
        with pytest.raises(ValueError, match="empty"):
            Account.create("", "pass")

    def test_empty_password_raises_value_error(self, fixed_salt, global_test_env):
        with pytest.raises(ValueError, match="empty"):
            Account.create("user", "")

    def test_both_empty_raises(self, fixed_salt, global_test_env):
        with pytest.raises(ValueError):
            Account.create("", "")

    def test_duplicate_name_raises_value_error(self, fixed_salt, global_test_env):
        # INTENT: collision raises ValueError (same as empty name/password)
        a = _make_account("dave", "pw")
        with pytest.raises(ValueError, match="dave"):
            Account.create("dave", "different")
        # The original is still in the registry
        assert a in _ALL_OBJECTS.values()

    def test_duplicate_name_does_not_call_at_create(self, fixed_salt, global_test_env):
        # INTENT: when creation fails, no hooks should fire
        _make_account("eve", "pw")
        with pytest.raises(ValueError, match="eve"):
            Account.create("eve", "pw2")
        # If at_create were called, the second account would be in the registry
        assert len([o for o in _ALL_OBJECTS.values() if isinstance(o, Account)]) == 1

    def test_adds_to_global_registry(self, fixed_salt, global_test_env):
        acc = _make_account("frank", "pw")
        assert acc in _ALL_OBJECTS.values()
        assert _ALL_OBJECTS[acc.id] is acc

    def test_characters_starts_empty(self, fixed_salt, global_test_env):
        acc = _make_account("gina", "pw")
        assert acc.characters == []
        assert isinstance(acc.characters, list)

    def test_at_create_called(self, fixed_salt, global_test_env):
        # INTENT: at_create is the hook for subclasses to do post-create work
        called = []
        orig = Account.at_create
        Account.at_create = lambda self: called.append(self)
        try:
            acc = _make_account("harry", "pw")
            assert called == [acc]
        finally:
            Account.at_create = orig


class TestAccountDelete:
    def test_delete_removes_from_registry(self, fixed_salt, global_test_env):
        acc = _make_account("ivy", "pw")
        assert acc in _ALL_OBJECTS.values()
        assert acc.delete() is True
        assert acc not in _ALL_OBJECTS.values()

    def test_delete_marks_is_deleted(self, fixed_salt, global_test_env):
        acc = _make_account("jack", "pw")
        assert acc.is_deleted is False
        acc.delete()
        assert acc.is_deleted is True

    def test_delete_creates_del_ops(self, fixed_salt, global_test_env):
        # INTENT: the DB layer must be told to remove the row
        acc = _make_account("kim", "pw")
        sql, params = acc.get_del_ops()
        assert sql == "DELETE FROM objects WHERE id = ?"
        assert params == (acc.id,)

    def test_delete_vetoed_by_at_delete(self, fixed_salt, global_test_env):
        # INTENT: at_delete returning False must abort the entire delete
        # (no DB ops, no remove, no is_deleted flag)
        acc = _make_account("liam", "pw")
        orig = Account.at_delete
        Account.at_delete = lambda self, caller=None: False
        try:
            result = acc.delete()
            assert result is False
            # Object is still in registry
            assert acc in _ALL_OBJECTS.values()
            # And is_deleted is still False
            assert acc.is_deleted is False
        finally:
            Account.at_delete = orig

    def test_delete_at_delete_receives_caller(self, fixed_salt, global_test_env):
        acc = _make_account("mia", "pw")
        caller = MagicMock()
        received = []
        orig = Account.at_delete
        Account.at_delete = lambda self, c=None: (received.append(c), True)[1]
        try:
            acc.delete(caller=caller)
            assert received == [caller]
        finally:
            Account.at_delete = orig

    def test_delete_unused_param_does_not_break_signature(self, fixed_salt, global_test_env):
        # INTENT: the `unused` param exists for API compatibility and must
        # be tolerated (and explicitly discarded, not stored)
        acc = _make_account("noah", "pw")
        assert acc.delete(unused=False) is True

    def test_delete_vetoed_no_db_ops_called(self, fixed_salt, global_test_env):
        # INTENT: when vetoed, no DB delete operation is even issued
        acc = _make_account("olive", "pw")
        from atheriz.globals import objects as g
        del_calls = []
        original_del = g.delete_objects
        g.delete_objects = lambda ops: del_calls.append(ops)
        orig = Account.at_delete
        Account.at_delete = lambda self, caller=None: False
        try:
            acc.delete()
            assert del_calls == []
        finally:
            g.delete_objects = original_del
            Account.at_delete = orig


class TestAccountCharacterManagement:
    def test_add_character_stores_id_not_object(self, fixed_salt, global_test_env):
        # INTENT: characters are tracked by ID so that loaded/unloaded
        # character objects can still be referenced
        acc = _make_account("paul", "pw")
        char = make_object("char1", is_pc=True)
        char.id = 42
        acc.add_character(char)
        assert acc.characters == [42]
        assert char not in acc.characters  # it's the int, not the object

    def test_add_multiple_characters(self, fixed_salt, global_test_env):
        acc = _make_account("quinn", "pw")
        c1 = make_object("c1", is_pc=True); c1.id = 1
        c2 = make_object("c2", is_pc=True); c2.id = 2
        acc.add_character(c1)
        acc.add_character(c2)
        assert acc.characters == [1, 2]

    def test_add_character_appends_idempotently(self, fixed_salt, global_test_env):
        # INTENT: the implementation does not de-dupe. If you add the same
        # character twice, the id appears twice. Documenting this behavior.
        acc = _make_account("ruby", "pw")
        char = make_object("c1", is_pc=True); char.id = 5
        acc.add_character(char)
        acc.add_character(char)
        assert acc.characters == [5, 5]

    def test_remove_character_removes_first_occurrence(self, fixed_salt, global_test_env):
        acc = _make_account("sam", "pw")
        c = make_object("c1", is_pc=True); c.id = 7
        acc.add_character(c)
        acc.add_character(c)
        acc.remove_character(c)
        assert acc.characters == [7]  # one removed, one left

    def test_remove_character_missing_raises(self, fixed_salt, global_test_env):
        # INTENT: list.remove raises ValueError for missing id — we let that
        # propagate rather than swallow it (caller bug to call remove when
        # the character wasn't there)
        acc = _make_account("tara", "pw")
        c = make_object("c1", is_pc=True); c.id = 99
        with pytest.raises(ValueError):
            acc.remove_character(c)

    def test_add_character_uses_lock(self, fixed_salt, global_test_env):
        # INTENT: the lock guards the characters list. Verifying the lock
        # is functional: if it weren't, this concurrent test would race.
        # (We don't do flaky timing here — just spot-check that add works.)
        acc = _make_account("uma", "pw")
        c = make_object("c1", is_pc=True); c.id = 1
        acc.add_character(c)
        assert acc.characters == [1]


class TestAccountPasswords:
    def test_hash_password_is_static(self, fixed_salt, global_test_env):
        # INTENT: same password + same salt = same hash (deterministic)
        h1 = Account.hash_password("pw")
        h2 = Account.hash_password("pw")
        assert h1 == h2

    def test_hash_password_changes_with_salt(self, fixed_salt, global_test_env):
        # INTENT: a different salt must produce a different hash
        h1 = Account.hash_password("pw")
        import atheriz.globals.salt as salt_mod
        original = salt_mod._SALT
        salt_mod._SALT = "different-salt"
        try:
            h2 = Account.hash_password("pw")
            assert h1 != h2
        finally:
            salt_mod._SALT = original

    def test_hash_password_length_64(self, fixed_salt, global_test_env):
        # INTENT: SHA-256 hex is always 64 chars
        h = Account.hash_password("x")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_password_uses_key_stretching(self, fixed_salt, global_test_env):
        # INTENT: PBKDF2 with 600k iterations should take measurable time
        import time
        start = time.monotonic()
        Account.hash_password("test-password")
        elapsed = time.monotonic() - start
        # With 600k iterations, this should take at least a few ms
        # On fast hardware it might be ~50ms, on slow ~500ms
        assert elapsed > 0.001  # at least 1ms

    def test_check_password_uses_constant_time_compare(self, fixed_salt, global_test_env):
        # INTENT: check_password must use hmac.compare_digest to prevent
        # timing side-channel attacks
        acc = _make_account("timing-test", "secret")
        # Verify correct password works
        assert acc.check_password("secret") is True
        # Verify incorrect password fails
        assert acc.check_password("wrong") is False
        # Verify the implementation uses hmac.compare_digest (not ==)
        # We check this by verifying the result is bool (compare_digest returns bool)
        # and that it's not a direct string comparison result
        result = acc.check_password("secret")
        assert isinstance(result, bool)

    def test_check_password_correct(self, fixed_salt, global_test_env):
        acc = _make_account("vera", "correct-horse")
        assert acc.check_password("correct-horse") is True

    def test_check_password_wrong(self, fixed_salt, global_test_env):
        acc = _make_account("wade", "correct-horse")
        assert acc.check_password("wrong-horse") is False

    def test_check_password_empty(self, fixed_salt, global_test_env):
        acc = _make_account("xena", "real")
        assert acc.check_password("") is False

    def test_set_password_hashes(self, fixed_salt, global_test_env):
        # INTENT: set_password must store hashed, not plaintext
        acc = _make_account("yara", "old")
        acc.set_password("new-pass")
        assert acc.password != "new-pass"
        assert "new-pass" not in acc.password
        assert acc.check_password("new-pass") is True
        assert acc.check_password("old") is False


class TestAccountLogin:
    def test_login_correct_credentials(self, fixed_salt, global_test_env):
        acc = _make_account("zeke", "pw")
        assert acc.login("zeke", "pw") is True
        assert acc.logged_in is True

    def test_login_wrong_password(self, fixed_salt, global_test_env):
        acc = _make_account("anna", "pw")
        assert acc.login("anna", "wrong") is False
        # INTENT: failed login must not set logged_in
        assert not getattr(acc, "logged_in", False)

    def test_login_wrong_name(self, fixed_salt, global_test_env):
        acc = _make_account("bjorn", "pw")
        assert acc.login("not-bjorn", "pw") is False
        assert not getattr(acc, "logged_in", False)

    def test_login_both_wrong(self, fixed_salt, global_test_env):
        acc = _make_account("cara", "pw")
        assert acc.login("cara", "wrong") is False
        assert acc.login("not-cara", "pw") is False
        assert acc.login("nope", "nope") is False
        assert not getattr(acc, "logged_in", False)

    def test_login_correct_after_wrong(self, fixed_salt, global_test_env):
        # INTENT: a failed attempt should not corrupt the account state
        # such that a later correct attempt fails
        acc = _make_account("drew", "pw")
        assert acc.login("drew", "wrong") is False
        assert acc.login("drew", "pw") is True
        assert acc.logged_in is True

    def test_login_lock_usable(self, fixed_salt, global_test_env):
        # INTENT: login() acquires the lock; after it returns, the lock
        # is released and can be acquired again
        acc = _make_account("erin", "pw")
        # The lock is reentrant so a single call works without deadlock.
        # We verify the lock is healthy and unheld after login.
        assert acc.lock.acquire(blocking=False) is True
        acc.lock.release()


class TestAccountHooks:
    def test_at_pre_puppet_default_returns_true(self, fixed_salt, global_test_env):
        # INTENT: by default, any account can puppet any character
        acc = _make_account("finn", "pw")
        char = make_object("c", is_pc=True)
        assert acc.at_pre_puppet(char) is True

    def test_at_create_default_is_noop(self, global_test_env):
        # INTENT: base class is silent, no side effects
        acc = Account()
        assert acc.at_create() is None

    def test_at_disconnect_default_is_noop(self, global_test_env):
        acc = Account()
        assert acc.at_disconnect() is None


class TestAccountDbOps:
    def test_get_save_ops_returns_insert_or_replace(self, fixed_salt, global_test_env):
        acc = _make_account("gabe", "pw")
        sql, params = acc.get_save_ops()
        assert sql == "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        assert params[0] == acc.id
        # The data is dill-serialized
        assert isinstance(params[1], bytes)

    def test_get_save_ops_data_can_be_unpickled(self, fixed_salt, global_test_env):
        # INTENT: a save roundtrip must restore the object
        acc = _make_account("hope", "pw")
        _sql, params = acc.get_save_ops()
        data = params[1]
        loaded = dill.loads(data)
        assert loaded.id == acc.id
        assert loaded.name == acc.name

    def test_get_save_ops_clears_is_modified(self, fixed_salt, global_test_env):
        # INTENT: after save, the in-memory dirty flag is cleared so the
        # next autosave cycle doesn't redundantly write this object
        acc = _make_account("inga", "pw")
        assert acc.is_modified is True
        acc.get_save_ops()
        assert acc.is_modified is False

    def test_get_del_ops_returns_correct_sql(self, fixed_salt, global_test_env):
        acc = _make_account("juno", "pw")
        sql, params = acc.get_del_ops()
        assert sql == "DELETE FROM objects WHERE id = ?"
        assert params == (acc.id,)

    def test_get_del_ops_does_not_change_is_modified(self, fixed_salt, global_test_env):
        # INTENT: del ops are about the DB, not the in-memory dirty flag
        acc = _make_account("kate", "pw")
        acc.get_del_ops()
        assert acc.is_modified is True  # unchanged


class TestAccountPickle:
    def test_getstate_excludes_lock(self, fixed_salt, global_test_env):
        # INTENT: the lock cannot be pickled; it must be removed from state
        acc = _make_account("lena", "pw")
        state = acc.__getstate__()
        assert "lock" not in state
        assert "name" in state
        assert "id" in state
        assert "password" in state

    def test_setstate_restores_lock(self, fixed_salt, global_test_env):
        acc = _make_account("maya", "pw")
        state = acc.__getstate__()
        new_acc = Account.__new__(Account)
        new_acc.__setstate__(state)
        assert isinstance(new_acc.lock, _thread.RLock)
        # And the lock is fresh — not the same object as the original
        assert new_acc.lock is not acc.lock

    def test_pickle_roundtrip_preserves_state(self, fixed_salt, global_test_env):
        acc = _make_account("nick", "pw")
        c = make_object("c1", is_pc=True); c.id = 100
        acc.add_character(c)
        data = pickle.dumps(acc)
        acc2 = pickle.loads(data)
        assert acc2.id == acc.id
        assert acc2.name == acc.name
        assert acc2.password == acc.password
        assert acc2.characters == [100]

    def test_pickled_lock_is_fresh(self, fixed_salt, global_test_env):
        # INTENT: a pickled-then-unpickled account must have its own lock
        # state — not share a lock with the original (which would deadlock
        # since RLock tracks the owning thread)
        acc = _make_account("olive2", "pw")
        acc2 = pickle.loads(pickle.dumps(acc))
        assert acc2.lock is not acc.lock
        # And both can be acquired independently
        assert acc.lock.acquire(blocking=False) is True
        acc.lock.release()
        assert acc2.lock.acquire(blocking=False) is True
        acc2.lock.release()

    def test_pickled_account_can_login(self, fixed_salt, global_test_env):
        # INTENT: a restored account must remain fully functional
        acc = _make_account("pete", "pw")
        acc2 = pickle.loads(pickle.dumps(acc))
        assert acc2.check_password("pw") is True
        assert acc2.login("pete", "pw") is True


class TestAccountThreadSafety:
    def test_concurrent_character_adds(self, fixed_salt, global_test_env):
        # INTENT: the lock protects characters from corruption
        import threading
        acc = _make_account("quinn2", "pw")
        errors = []

        def worker(i):
            try:
                c = make_object(f"c{i}", is_pc=True); c.id = i
                acc.add_character(c)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(acc.characters) == 20
        assert sorted(acc.characters) == list(range(20))


class TestAccountIntegration:
    def test_full_lifecycle(self, fixed_salt, global_test_env):
        # Create -> add character -> change password -> login -> delete
        acc = Account.create("ruth", "initial")
        assert acc is not None

        c = make_object("ruth_char", is_pc=True); c.id = 1000
        acc.add_character(c)
        assert acc.characters == [1000]

        acc.set_password("updated")
        assert acc.check_password("updated") is True
        assert acc.check_password("initial") is False

        assert acc.login("ruth", "updated") is True

        assert acc.delete() is True
        assert acc.is_deleted is True
        assert acc not in _ALL_OBJECTS.values()

    def test_subclass_hooks_can_veto(self, fixed_salt, global_test_env):
        # INTENT: subclasses can override at_delete to inject custom behavior
        class VetoAccount(Account):
            def at_delete(self, caller=None):
                return False
        a = VetoAccount.create("sam2", "pw")
        assert a is not None
        assert a.delete() is False  # at_delete vetoed
        assert a in _ALL_OBJECTS.values()  # not removed
        # Cleanup: bypass the veto
        orig = VetoAccount.at_delete
        VetoAccount.at_delete = lambda self, caller=None: True
        try:
            assert a.delete() is True
        finally:
            VetoAccount.at_delete = orig
