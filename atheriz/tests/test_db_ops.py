"""Tests for atheriz.objects.base_db_ops — DbOps save/delete serialization.

The DbOps mixin provides get_save_ops and get_del_ops for persistence.
These tests verify the SQL/params format and that round-trips work.
"""
from __future__ import annotations

import dill
import pytest

from atheriz.objects.base_db_ops import DbOps
from atheriz.tests.fakes import make_object


class _DbHolder(DbOps):
    """Plain subclass for testing."""
    pass


class TestSaveOps:
    def test_returns_tuple_of_sql_and_params(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 42
        result = obj.get_save_ops()
        assert isinstance(result, tuple)
        assert len(result) == 2
        sql, params = result

    def test_sql_is_insert_or_replace(self, global_test_env):
        # INTENT: save uses INSERT OR REPLACE so the same row can be
        # upserted (avoids separate update-vs-insert logic)
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        sql, _ = obj.get_save_ops()
        assert sql == "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"

    def test_params_contain_id(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 99
        _sql, params = obj.get_save_ops()
        assert params[0] == 99

    def test_params_data_is_dill_bytes(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        _sql, params = obj.get_save_ops()
        assert isinstance(params[1], bytes)

    def test_data_can_be_unpickled(self, global_test_env):
        # INTENT: the serialized blob must be deserializable
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.label = "test-label"
        _sql, params = obj.get_save_ops()
        loaded = dill.loads(params[1])
        assert loaded.id == 1
        assert loaded.label == "test-label"

    def test_save_clears_is_modified(self, global_test_env):
        # INTENT: after save, is_modified is False so the next autosave
        # cycle won't redundantly write this object
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.is_modified = True
        obj.get_save_ops()
        assert obj.is_modified is False

    def test_save_uses_lock(self, monkeypatch, global_test_env):
        # INTENT: the lock guards the state during serialization
        obj = _DbHolder()
        import _thread
        real_lock = _thread.RLock()
        obj.lock = real_lock

        acquired = []
        class SpyLock:
            def __enter__(self_):
                acquired.append(True)
                return real_lock.__enter__()
            def __exit__(self_, *a):
                return real_lock.__exit__(*a)

        obj.lock = SpyLock()
        obj.id = 1
        obj.get_save_ops()
        assert acquired == [True]

    def test_save_uses_object_setattr_to_set_modified(self, global_test_env):
        # INTENT: is_modified is set with object.__setattr__ to bypass
        # any thread-safe wrapper that might be in place
        # (This is the implementation detail: the source uses
        #  `object.__setattr__(self, "is_modified", False)`)
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        # If is_modified were set via a property that raises, this would fail.
        # Verify the basic path:
        obj.is_modified = True
        obj.get_save_ops()
        assert obj.is_modified is False


class TestDelOps:
    def test_returns_tuple(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        result = obj.get_del_ops()
        assert isinstance(result, tuple)
        assert len(result) == 2
        sql, params = result

    def test_sql_is_delete_by_id(self, global_test_env):
        # INTENT: delete uses primary key (id) for the WHERE clause
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        sql, _ = obj.get_del_ops()
        assert sql == "DELETE FROM objects WHERE id = ?"

    def test_params_contain_id(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        _sql, params = obj.get_del_ops()
        assert params == (5,)

    def test_del_ops_does_not_change_is_modified(self, global_test_env):
        # INTENT: del ops are not "dirty" (they don't need a save)
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        obj.is_modified = True
        obj.get_del_ops()
        assert obj.is_modified is True

    def test_del_ops_works_with_negative_id(self, global_test_env):
        # Negative ids shouldn't be a special case for del ops
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = -1
        _sql, params = obj.get_del_ops()
        assert params == (-1,)


class TestDbOpsIntegration:
    def test_save_then_del_operations_consistent(self, global_test_env):
        # INTENT: save produces an upsert, del produces a delete; both
        # agree on the id
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 7
        save_sql, _ = obj.get_save_ops()
        del_sql, del_params = obj.get_del_ops()
        # Different SQL, same id-targeted scope
        assert "INSERT OR REPLACE" in save_sql
        assert "DELETE" in del_sql
        assert del_params == (7,)

    def test_works_with_real_object(self, global_test_env):
        # INTENT: DbOps works as a mixin with real subclasses
        obj = make_object("real", is_item=True)
        obj.id = 123
        save_sql, save_params = obj.get_save_ops()
        del_sql, del_params = obj.get_del_ops()
        assert save_params[0] == 123
        assert del_params == (123,)

    def test_modifications_then_save(self, global_test_env):
        # INTENT: a sequence of state changes followed by save is supported
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.field1 = "a"
        obj.get_save_ops()
        assert obj.is_modified is False
        # Mutate, then save again
        obj.field1 = "b"
        obj.is_modified = True
        obj.get_save_ops()
        assert obj.is_modified is False
        # And the new state is in the saved blob
        _sql, params = obj.get_save_ops()
        loaded = dill.loads(params[1])
        assert loaded.field1 == "b"
