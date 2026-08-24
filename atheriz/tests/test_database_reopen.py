"""Issue tests: #10 — `get_database()` after a `close()` silently reopens a
brand-new SQLite connection instead of failing, which masks the "database
already closed" state everywhere and makes the double-shutdown in #5 "work"
while a fresh store is used.

INTENT: any use of the database after it has been closed must raise loudly so
the closed-state can never be hidden behind a freshly re-created connection.
"""
from __future__ import annotations

import pytest

from atheriz import database_setup


def test_get_database_after_close_must_raise(global_test_env):
    """INTENT: after close, `get_database()` must raise a closed-state error.
    Today it silently reopens and returns a fresh connection -> no raise -> FAIL."""
    db = database_setup.get_database()
    db.close()

    with pytest.raises(Exception):
        database_setup.get_database()


def test_game_operations_fail_after_close(global_test_env):
    """INTENT: running SQL against the store after it was closed must raise an
    explicit closed-state error, never succeed on a silent re-created DB."""
    db = database_setup.get_database()
    db.close()

    with pytest.raises(Exception):
        reopened = database_setup.get_database()
        cursor = reopened.connection.cursor()
        cursor.execute("SELECT 1")