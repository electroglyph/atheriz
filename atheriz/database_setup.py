
import sqlite3
import os
from . import settings
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite3 import Connection

_INIT_LOCK = Lock()

class Database:
    def __init__(self, connection: Connection):
        self.lock = Lock()
        self.connection = connection


_DATABASE: Database | None = None

def get_database():
    """
    Grabs a cache global copy of the sqlite connection used to access the db.
    """
    global _DATABASE
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
    conn = get_database().connection
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS objects (id INTEGER PRIMARY KEY, data BLOB)")
    cursor.execute("CREATE TABLE IF NOT EXISTS mapdata (area TEXT, z INTEGER, data BLOB, PRIMARY KEY (area, z))")
    cursor.execute("CREATE TABLE IF NOT EXISTS areas (name TEXT PRIMARY KEY, data BLOB)")
    cursor.execute("CREATE TABLE IF NOT EXISTS transitions (to_area TEXT, to_x INTEGER, to_y INTEGER, to_z INTEGER, data BLOB, PRIMARY KEY (to_area, to_x, to_y, to_z))")
    cursor.execute("CREATE TABLE IF NOT EXISTS doors (area TEXT, x INTEGER, y INTEGER, z INTEGER, data BLOB, PRIMARY KEY (area, x, y, z))")
    conn.commit()