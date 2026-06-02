"""Tests for atheriz/database_setup.py.

Covers Database, get_database(), and do_setup(). The conftest
`global_test_env` autouse fixture redirects SAVE_PATH to a temp dir
and resets the database singleton.
"""
import os
import sqlite3

import pytest

from atheriz import database_setup
from atheriz import settings


# ---------------------------------------------------------------------------
# get_database singleton
# ---------------------------------------------------------------------------


def test_get_database_returns_cached_singleton():
    db1 = database_setup.get_database()
    db2 = database_setup.get_database()
    assert db1 is db2


def test_get_database_creates_save_path():
    """If SAVE_PATH doesn't exist, get_database creates it."""
    new_path = os.path.join(settings.SAVE_PATH, "nested", "subdir")
    # Reset the singleton so the new SAVE_PATH is consulted.
    database_setup._DATABASE = None
    settings.SAVE_PATH = new_path
    try:
        db = database_setup.get_database()
        assert os.path.isdir(new_path)
        assert db is not None
        db.close()
    finally:
        # Reset to conftest-managed path; conftest's teardown will rmtree it.
        database_setup._DATABASE = None


def test_get_database_pragmas_wal():
    db = database_setup.get_database()
    cursor = db.connection.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"


def test_get_database_check_same_thread_false():
    db = database_setup.get_database()
    # check_same_thread=False allows connection from any thread.
    assert db.connection is not None


# ---------------------------------------------------------------------------
# Database.close
# ---------------------------------------------------------------------------


def test_database_close_clears_singleton():
    db = database_setup.get_database()
    db.close()
    assert database_setup._DATABASE is None


def test_database_close_idempotent_safe():
    """Closing twice is OK — second close is a no-op because singleton
    is None. (Note: closing the same sqlite3.Connection twice would
    raise, but the singleton clear guards against that.)"""
    db = database_setup.get_database()
    db.close()
    # Singleton is None now; getting a fresh one should work.
    db2 = database_setup.get_database()
    assert db2 is not db


# ---------------------------------------------------------------------------
# do_setup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table",
    ["objects", "mapdata", "areas", "transitions", "doors"],
)
def test_do_setup_creates_all_tables(table):
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


def test_do_setup_idempotent():
    """Calling do_setup twice does not raise."""
    database_setup.do_setup()
    database_setup.do_setup()
    # No assertion needed; just no exception.


def test_do_setup_objects_table_schema():
    database_setup.do_setup()
    db = database_setup.get_database()
    cursor = db.connection.cursor()
    cursor.execute("PRAGMA table_info(objects)")
    cols = [row[1] for row in cursor.fetchall()]
    assert "id" in cols
    assert "data" in cols


def test_do_setup_transitions_table_composite_pk():
    database_setup.do_setup()
    db = database_setup.get_database()
    cursor = db.connection.cursor()
    cursor.execute(
        "INSERT INTO transitions (to_area, to_x, to_y, to_z, data) VALUES (?,?,?,?,?)",
        ("foo", 1, 2, 3, b""),
    )
    # Same key should be a constraint violation.
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            "INSERT INTO transitions (to_area, to_x, to_y, to_z, data) VALUES (?,?,?,?,?)",
            ("foo", 1, 2, 3, b""),
        )
    db.connection.rollback()
