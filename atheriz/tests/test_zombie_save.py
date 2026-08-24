"""Regression tests for zombie resurrection via in-flight save checkpoints.

save_objects() snapshotted objects before opening its DB transaction and wrote
each with INSERT OR REPLACE. An object deleted between the snapshot and the
INSERT had its row resurrected; the zombie persisted to disk and reappeared on
next boot. The fix filters deleted objects at snapshot time and re-checks
(deleted flag + registry presence) immediately before each write.
"""

from __future__ import annotations

from atheriz import database_setup
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import (
    delete_objects,
    remove_object,
    save_objects,
)


def _row_count(obj_id: int) -> int:
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM objects WHERE id = ?", (obj_id,))
        return cur.fetchone()[0]


def test_deleted_object_skipped_at_snapshot(global_test_env):
    """INTENT: an object flagged deleted (and unregistered) must never reach
    the objects table, even with force=True."""
    victim = Object.create(None, "ghost")
    victim.desc = "dirty"
    assert victim.is_modified is True

    victim.is_deleted = True
    remove_object(victim)

    save_objects(force=True)

    assert _row_count(victim.id) == 0


def test_delete_between_snapshot_and_write_is_not_resurrected(global_test_env, monkeypatch):
    """INTENT: the execute-time re-check must skip an object whose delete
    completes after save_objects() snapshots it but before its row is written.
    Without the re-check this test fails: INSERT OR REPLACE resurrects the row."""
    victim = Object.create(None, "victim")
    victim.desc = "first version"
    save_objects()

    victim.name = "about-to-die"
    assert victim.is_modified is True

    db = database_setup.get_database()
    real_connection = db.connection
    state = {"deleted": False}

    class ConnProxy:
        def __init__(self, inner):
            self._inner = inner

        def cursor(self):
            if not state["deleted"]:
                state["deleted"] = True
                victim.is_deleted = True
                delete_objects([victim.get_del_ops()])
                remove_object(victim)
            return self._inner.cursor()

        def __getattr__(self, item):
            return getattr(self._inner, item)

    monkeypatch.setattr(db, "connection", ConnProxy(real_connection))

    save_objects(force=True)

    assert _row_count(victim.id) == 0


def test_live_dirty_object_still_saves(global_test_env):
    """INTENT: the deleted-object guards must not interfere with normal saves."""
    survivor = Object.create(None, "survivor")
    survivor.desc = "still here"
    assert survivor.is_modified is True

    save_objects()

    assert _row_count(survivor.id) == 1
    assert survivor.is_modified is False
