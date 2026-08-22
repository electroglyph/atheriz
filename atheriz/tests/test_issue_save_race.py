"""Regression tests for the save-checkpoint lost-update race.

save_objects() used to clear ``is_modified`` unconditionally *after* COMMIT.
A mutation landing between serialization (inside ``get_save_ops()``) and the
post-commit clear had its flag wiped, so the change never reached disk until
something unrelated re-marked the object dirty. The fix serializes and clears
the flag atomically under the object lock (``get_save_ops_clearing()``), so
any later mutation naturally re-raises the flag.
"""

from __future__ import annotations

import dill
import pytest

from atheriz import database_setup
from atheriz.objects import base_db_ops
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import get, load_objects, save_objects


def _stored_object(obj_id: int):
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id = ?", (obj_id,))
        row = cur.fetchone()
    return dill.loads(row[0]) if row else None


def test_mutation_during_checkpoint_is_not_lost(global_test_env, monkeypatch):
    """INTENT: a mutation that lands after an object's serialization point but
    before the checkpoint finishes must keep the object dirty so the next
    checkpoint persists it."""
    alpha = Object.create(None, "alpha")
    beta = Object.create(None, "beta")
    save_objects()
    assert alpha.is_modified is False
    assert beta.is_modified is False

    real_dumps = base_db_ops.dill.dumps

    def racing_dumps(obj, *args, **kwargs):
        blob = real_dumps(obj, *args, **kwargs)
        if getattr(obj, "id", None) == beta.id:
            alpha.name = "mutated-during-checkpoint"
            alpha.desc = "mutated"
        return blob

    monkeypatch.setattr(base_db_ops.dill, "dumps", racing_dumps)

    alpha.name = "pre-mutation"
    beta.name = "trigger"
    assert alpha.is_modified is True
    assert beta.is_modified is True

    save_objects()

    assert alpha.name == "mutated-during-checkpoint"
    stored = _stored_object(alpha.id)
    assert stored.name == "pre-mutation"
    assert alpha.is_modified is True

    monkeypatch.undo()
    save_objects()
    assert alpha.is_modified is False
    assert _stored_object(alpha.id).name == "mutated-during-checkpoint"


def test_serialization_failure_restores_flag(global_test_env, monkeypatch):
    """INTENT: if dill.dumps raises inside get_save_ops_clearing, the object's
    prior flag state must be restored (and save_objects' rollback path also
    re-marks attempted objects)."""
    obj = Object.create(None, "doomed")
    obj.name = "dirty-before-failure"
    assert obj.is_modified is True

    def boom(*args, **kwargs):
        raise RuntimeError("serialize fail")

    monkeypatch.setattr(base_db_ops.dill, "dumps", boom)
    with pytest.raises(RuntimeError):
        obj.get_save_ops_clearing()
    assert obj.is_modified is True


def test_clean_flag_persists_across_restart_after_save(global_test_env):
    """INTENT: the blob must store is_modified=False for saved objects so a
    reload does not mark every loaded object dirty at boot."""
    from atheriz.globals.objects import _ALL_OBJECTS

    obj = Object.create(None, "persist-me")
    obj.desc = "some description"
    save_objects()

    database_setup._DATABASE.close()
    database_setup._CLOSED = False
    _ALL_OBJECTS.clear()
    load_objects()
    reloaded = get(obj.id)
    assert reloaded is not None
    assert reloaded[0].is_modified is False


def test_get_save_ops_clearing_consumes_flag_immediately(global_test_env):
    """INTENT: get_save_ops_clearing() must consume the in-memory dirty flag
    at serialization time (before any COMMIT), and the blob it produces must
    store the flag as False."""
    obj = Object.create(None, "clearme")
    obj.desc = "dirty"
    assert obj.is_modified is True

    sql, params = obj.get_save_ops_clearing()

    assert obj.is_modified is False
    assert dill.loads(params[1]).is_modified is False
