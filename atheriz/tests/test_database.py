"""Tests for atheriz/database_setup.py and atheriz/objects/base_db_ops.py."""
from __future__ import annotations

import os
import sqlite3
import threading

import dill
import pytest

from atheriz import database_setup
from atheriz import settings
from atheriz.objects.base_db_ops import DbOps
from atheriz.tests.fakes import make_object


class _DbHolder(DbOps):
    pass


class TestDatabaseSetup:
    def test_get_database_returns_cached_singleton(self):
        db1 = database_setup.get_database()
        db2 = database_setup.get_database()
        assert db1 is db2

    def test_get_database_creates_save_path(self):
        new_path = os.path.join(settings.SAVE_PATH, "nested", "subdir")
        database_setup._DATABASE = None
        settings.SAVE_PATH = new_path
        try:
            db = database_setup.get_database()
            assert os.path.isdir(new_path)
            assert db is not None
            db.close()
        finally:
            database_setup._DATABASE = None

    def test_get_database_pragmas_wal(self):
        db = database_setup.get_database()
        cursor = db.connection.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"

    def test_get_database_check_same_thread_false(self):
        db = database_setup.get_database()
        assert db.connection is not None

    def test_database_close_clears_singleton(self):
        db = database_setup.get_database()
        db.close()
        assert database_setup._DATABASE is None

    def test_database_close_idempotent_safe(self):
        db = database_setup.get_database()
        db.close()
        db.close()
        assert database_setup._DATABASE is None

    def test_database_close_no_toctou(self):
        errors = []

        def closer():
            try:
                db = database_setup.get_database()
                db.close()
            except Exception as e:
                errors.append(e)

        def getter():
            try:
                for _ in range(50):
                    db = database_setup.get_database()
                    with db.lock:
                        db.connection.execute("SELECT 1")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=closer)]
        threads += [threading.Thread(target=getter) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        unexpected = [e for e in errors if "closed" not in str(e).lower()]
        assert unexpected == [], f"unexpected errors: {unexpected}"
        with pytest.raises(Exception):
            database_setup.get_database()

    def test_reopen_database_after_close_restores_access(self):
        db = database_setup.get_database()
        db.close()

        with pytest.raises(RuntimeError):
            database_setup.get_database()

        database_setup.reopen_database()
        reopened = database_setup.get_database()
        assert reopened is not db
        with reopened.lock:
            reopened.connection.execute("SELECT 1")

    def test_reopen_database_survives_close_reopen_cycles(self):
        for _ in range(3):
            database_setup.get_database().close()
            with pytest.raises(RuntimeError):
                database_setup.get_database()
            database_setup.reopen_database()
            db = database_setup.get_database()
            with db.lock:
                db.connection.execute("SELECT 1")

    def test_do_setup_works_after_close_and_reopen(self):
        database_setup.get_database().close()
        database_setup.reopen_database()
        database_setup.do_setup()
        db = database_setup.get_database()
        cursor = db.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='objects'")
        assert cursor.fetchone() is not None

    @pytest.mark.parametrize(
        "table",
        ["objects", "mapdata", "areas", "transitions", "doors"],
    )
    def test_do_setup_creates_all_tables(self, table):
        database_setup.do_setup()
        db = database_setup.get_database()
        cursor = db.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        row = cursor.fetchone()
        assert row is not None, f"table {table} not created"
        assert row[0] == table

    def test_do_setup_idempotent(self):
        database_setup.do_setup()
        database_setup.do_setup()

    def test_do_setup_objects_table_schema(self):
        database_setup.do_setup()
        db = database_setup.get_database()
        cursor = db.connection.cursor()
        cursor.execute("PRAGMA table_info(objects)")
        cols = [row[1] for row in cursor.fetchall()]
        assert "id" in cols
        assert "data" in cols

    def test_do_setup_transitions_table_composite_pk(self):
        database_setup.do_setup()
        db = database_setup.get_database()
        cursor = db.connection.cursor()
        cursor.execute(
            "INSERT INTO transitions (to_area, to_x, to_y, to_z, data) VALUES (?,?,?,?,?)",
            ("foo", 1, 2, 3, b""),
        )
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO transitions (to_area, to_x, to_y, to_z, data) VALUES (?,?,?,?,?)",
                ("foo", 1, 2, 3, b""),
            )
        db.connection.rollback()


class TestDatabaseReopen:
    def test_get_database_after_close_must_raise(self, global_test_env):
        db = database_setup.get_database()
        db.close()

        with pytest.raises(Exception):
            database_setup.get_database()

    def test_game_operations_fail_after_close(self, global_test_env):
        db = database_setup.get_database()
        db.close()

        with pytest.raises(Exception):
            reopened = database_setup.get_database()
            cursor = reopened.connection.cursor()
            cursor.execute("SELECT 1")


class TestDbOps:
    def test_save_returns_tuple_of_sql_and_params(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 42
        result = obj.get_save_ops()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_save_sql_is_insert_or_replace(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        sql, _ = obj.get_save_ops()
        assert sql == "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"

    def test_save_params_contain_id(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 99
        _sql, params = obj.get_save_ops()
        assert params[0] == 99

    def test_save_params_data_is_dill_bytes(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        _sql, params = obj.get_save_ops()
        assert isinstance(params[1], bytes)

    def test_save_data_can_be_unpickled(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.label = "test-label"
        _sql, params = obj.get_save_ops()
        loaded = dill.loads(params[1])
        assert loaded.id == 1
        assert loaded.label == "test-label"

    def test_get_save_ops_does_not_clear_is_modified(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.is_modified = True
        obj.get_save_ops()
        assert obj.is_modified is True

    def test_save_uses_lock(self, monkeypatch, global_test_env):
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

    def test_flag_stays_dirty_across_repeated_save_ops(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.is_modified = True
        obj.get_save_ops()
        assert obj.is_modified is True
        obj.get_save_ops()
        assert obj.is_modified is True

    def test_del_returns_tuple(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        result = obj.get_del_ops()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_del_sql_is_delete_by_id(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        sql, _ = obj.get_del_ops()
        assert sql == "DELETE FROM objects WHERE id = ?"

    def test_del_params_contain_id(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        _sql, params = obj.get_del_ops()
        assert params == (5,)

    def test_del_ops_does_not_change_is_modified(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 5
        obj.is_modified = True
        obj.get_del_ops()
        assert obj.is_modified is True

    def test_del_ops_works_with_negative_id(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = -1
        _sql, params = obj.get_del_ops()
        assert params == (-1,)

    def test_save_then_del_operations_consistent(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 7
        save_sql, _ = obj.get_save_ops()
        del_sql, del_params = obj.get_del_ops()
        assert "INSERT OR REPLACE" in save_sql
        assert "DELETE" in del_sql
        assert del_params == (7,)

    def test_works_with_real_object(self, global_test_env):
        obj = make_object("real", is_item=True)
        obj.id = 123
        save_sql, save_params = obj.get_save_ops()
        del_sql, del_params = obj.get_del_ops()
        assert save_params[0] == 123
        assert del_params == (123,)

    def test_modifications_then_save(self, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.is_modified = True
        obj.field1 = "a"
        obj.get_save_ops()
        assert obj.is_modified is True
        obj.field1 = "b"
        obj.get_save_ops()
        assert obj.is_modified is True
        _sql, params = obj.get_save_ops()
        loaded = dill.loads(params[1])
        assert loaded.field1 == "b"

    def test_is_modified_stays_true_on_serialization_failure(self, monkeypatch, global_test_env):
        obj = _DbHolder()
        import _thread
        obj.lock = _thread.RLock()
        obj.id = 1
        obj.is_modified = True

        def boom(*a, **kw):
            raise RuntimeError("serialize fail")

        monkeypatch.setattr(dill, "dumps", boom)
        with pytest.raises(RuntimeError):
            obj.get_save_ops()
        assert obj.is_modified is True
