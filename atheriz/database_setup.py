from __future__ import annotations
import sqlite3
import os
from . import settings
from threading import Lock, RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite3 import Connection

_INIT_LOCK = Lock()
_DATABASE: Database | None = None
_CLOSED = False


class Database:
    def __init__(self, connection: Connection):
        self.lock = RLock()
        self.connection = connection

    def close(self):
        """Close the shared SQLite connection.

        All DB access must hold ``db.lock`` (see ``objects.py:190``,
        ``map.py:398`` for canonical examples). This method is only safe
        from quiesced contexts where no other thread holds ``db.lock`` or
        an open cursor — e.g. the ``reset`` command stops the server first
        (``atheriz.py:1186-1202``). Calling it while other threads are
        mid-statement will close the underlying connection underneath them.
        """
        global _DATABASE, _CLOSED
        with _INIT_LOCK:
            with self.lock:
                self.connection.close()
            _DATABASE = None
            _CLOSED = True


def reopen_database():
    """
    Explicitly allow `get_database()` to open a fresh connection after a
    `close()`. Used by the `reset` command, which closes the store to release
    file locks before deleting the data files.
    """
    global _CLOSED
    with _INIT_LOCK:
        _CLOSED = False


def get_database():
    """
    Grabs a cache global copy of the sqlite connection used to access the db.
    """
    global _DATABASE
    if _CLOSED:
        raise RuntimeError("database is closed; refusing to reopen")
    if _DATABASE is None:
        with _INIT_LOCK:
            if _DATABASE is not None:
                return _DATABASE
            if not os.path.exists(settings.SAVE_PATH):
                os.makedirs(settings.SAVE_PATH)
            db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
            c = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
            c.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
            _DATABASE = Database(c)
    return _DATABASE


def do_setup():
    """
    Creates a sqlite db at save folder/database.sqlite3 (check settings).
    """
    conn = get_database()
    with conn.lock:
        cursor = conn.connection.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS objects (id INTEGER PRIMARY KEY, data BLOB)")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS mapdata (area TEXT, z INTEGER, data BLOB, PRIMARY KEY (area, z))"
        )
        cursor.execute("CREATE TABLE IF NOT EXISTS areas (name TEXT PRIMARY KEY, data BLOB)")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS transitions (to_area TEXT, to_x INTEGER, to_y INTEGER, to_z INTEGER, data BLOB, PRIMARY KEY (to_area, to_x, to_y, to_z))"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS doors (area TEXT, x INTEGER, y INTEGER, z INTEGER, data BLOB, PRIMARY KEY (area, x, y, z))"
        )
        cursor.execute("CREATE TABLE IF NOT EXISTS gametime (id INTEGER PRIMARY KEY, data BLOB)")
        conn.connection.commit()
