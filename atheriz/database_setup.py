
import sqlite3
import os
from . import settings
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite3 import Connection

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
        if not os.path.exists(settings.SAVE_PATH):
            os.makedirs(settings.SAVE_PATH)
        db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
        c.commit()
        _DATABASE = Database(c)
    return _DATABASE

def do_setup():
    """
    Creates a sqlite db at save folder/database.sqlite3 (check settings).
    """
    conn = get_database().connection
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS objects (id INTEGER PRIMARY KEY, data BLOB)")
    conn.commit()