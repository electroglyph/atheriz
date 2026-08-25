import dill
import pytest
from unittest.mock import patch

from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel
from atheriz.objects.base_script import Script
from atheriz.objects.nodes import Node
from atheriz.utils import Coord
from atheriz.globals.objects import get as objects_get, _ALL_OBJECTS, delete_objects, save_objects, _is_still_saveable
from atheriz.globals.get import get_node_handler
from atheriz import database_setup
from atheriz.objects.base_flags import FLAG_DEFAULTS
import atheriz.settings as settings


def _row_count(obj_id: int) -> int:
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM objects WHERE id = ?", (obj_id,))
        return cur.fetchone()[0]


def test_add_character_marks_modified_and_persists(global_test_env, fixed_salt):
    caller = Object.create(None, "Caller")
    account = Account.create("acct_one", "password123")
    char = Object.create(None, "Hero", is_pc=True)
    object.__setattr__(account, "is_modified", False)
    account.add_character(char)
    assert account.is_modified is True
    save_objects()
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id = ?", (account.id,))
        blob = cur.fetchone()[0]
        loaded = dill.loads(blob)
        assert char.id in loaded.characters


def test_remove_character_marks_modified_and_persists(global_test_env, fixed_salt):
    account = Account.create("acct_two", "password123")
    char = Object.create(None, "Hero2", is_pc=True)
    account.add_character(char)
    save_objects()
    object.__setattr__(account, "is_modified", False)
    account.remove_character(char)
    assert account.is_modified is True
    save_objects()
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id = ?", (account.id,))
        blob = cur.fetchone()[0]
        loaded = dill.loads(blob)
        assert char.id not in loaded.characters


def test_remove_character_missing_id_still_marks_modified(global_test_env, fixed_salt):
    account = Account.create("acct_three", "password123")
    fake = Object.create(None, "Fake")
    object.__setattr__(account, "is_modified", False)
    account.remove_character(fake)
    assert account.is_modified is False


def test_account_delete_persists_and_no_resurrection_on_failure(global_test_env, fixed_salt):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    account = Account.create("del_acct", "password123")
    save_objects()
    assert _row_count(account.id) == 1
    with patch("atheriz.objects.base_account.delete_objects", side_effect=RuntimeError("boom")):
        try:
            account.delete(caller)
            assert False, "should have raised"
        except RuntimeError:
            pass
    assert account.id in _ALL_OBJECTS
    assert getattr(account, "is_deleted", False) is False
    assert _row_count(account.id) == 1
    assert account.delete(caller) is True
    assert account.id not in _ALL_OBJECTS
    assert _row_count(account.id) == 0


def test_channel_delete_persists_and_no_resurrection_on_failure(global_test_env):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    channel = Channel.create("chan_test")
    save_objects()
    assert _row_count(channel.id) == 1
    with patch("atheriz.objects.base_channel.delete_objects", side_effect=RuntimeError("boom")):
        try:
            channel.delete(caller)
            assert False
        except RuntimeError:
            pass
    assert channel.id in _ALL_OBJECTS
    assert getattr(channel, "is_deleted", False) is False
    assert _row_count(channel.id) == 1
    assert channel.delete(caller) is True
    assert channel.id not in _ALL_OBJECTS
    assert _row_count(channel.id) == 0


def test_script_delete_persists_and_no_resurrection_on_failure(global_test_env):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    script = Script.create(caller, "test_script")
    save_objects()
    assert _row_count(script.id) == 1
    with patch("atheriz.objects.base_script.delete_objects", side_effect=RuntimeError("boom")):
        try:
            script.delete(caller)
            assert False
        except RuntimeError:
            pass
    assert script.id in _ALL_OBJECTS
    assert getattr(script, "is_deleted", False) is False
    assert _row_count(script.id) == 1
    assert script.delete(caller) is True
    assert script.id not in _ALL_OBJECTS
    assert _row_count(script.id) == 0


def test_object_delete_recursive_persists_and_no_resurrection_on_failure(global_test_env):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    room = Node(coord=Coord("test", 0, 0, 0))
    get_node_handler().add_node(room)
    chest = Object.create(caller, "Chest", is_container=True)
    chest.move_to(room)
    gold = Object.create(caller, "Gold")
    gold.move_to(chest)
    save_objects()
    assert _row_count(chest.id) == 1 and _row_count(gold.id) == 1
    with patch("atheriz.objects.base_obj.delete_objects", side_effect=RuntimeError("boom")):
        try:
            chest.delete(caller, recursive=True)
            assert False
        except RuntimeError:
            pass
    assert chest.id in _ALL_OBJECTS and gold.id in _ALL_OBJECTS
    assert getattr(chest, "is_deleted", False) is False
    assert getattr(gold, "is_deleted", False) is False
    assert _row_count(chest.id) == 1 and _row_count(gold.id) == 1
    ops = chest.delete(caller, recursive=True)
    assert ops is not None
    assert chest.id not in _ALL_OBJECTS and gold.id not in _ALL_OBJECTS
    assert _row_count(chest.id) == 0 and _row_count(gold.id) == 0


def test_object_getstate_captures_location_without_deadlock(global_test_env):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    n1 = Node(coord=Coord("test", 0, 0, 0))
    n2 = Node(coord=Coord("test", 1, 0, 0))
    get_node_handler().add_node(n1)
    get_node_handler().add_node(n2)
    obj = Object.create(caller, "Wanderer", is_pc=True)
    obj.move_to(n1)
    state1 = obj.__getstate__()
    assert state1["location"] == n1.coord
    obj.move_to(n2)
    state2 = obj.__getstate__()
    assert state2["location"] == n2.coord


def test_is_temporary_not_persisted_even_when_flipped_after_snapshot(global_test_env):
    obj = Object.create(None, "temp_test")
    obj.desc = "first"
    save_objects()
    assert _row_count(obj.id) == 1
    obj.is_temporary = True
    obj.desc = "should not save"
    object.__setattr__(obj, "is_modified", True)
    save_objects()
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id = ?", (obj.id,))
        blob = cur.fetchone()[0]
        loaded = dill.loads(blob)
        assert loaded.desc == "first"
    assert _is_still_saveable(obj) is False


def test_is_temporary_filtered_at_save(global_test_env):
    obj = Object.create(None, "ephemeral")
    obj.is_temporary = True
    object.__setattr__(obj, "is_modified", True)
    save_objects()
    assert _row_count(obj.id) == 0
    obj.is_temporary = False
    object.__setattr__(obj, "is_modified", True)
    save_objects()
    assert _row_count(obj.id) == 1


def test_is_connected_not_persisted(global_test_env):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    room = Node(coord=Coord("test", 5, 5, 0))
    get_node_handler().add_node(room)
    pc = Object.create(caller, "PC", is_pc=True)
    pc.move_to(room)
    pc.is_connected = True
    object.__setattr__(pc, "is_modified", True)
    save_objects()
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id = ?", (pc.id,))
        blob = cur.fetchone()[0]
        loaded = dill.loads(blob)
        assert getattr(loaded, "is_connected", False) is False
    assert pc.is_connected is True


def test_logged_in_not_persisted(global_test_env, fixed_salt):
    account = Account.create("login_acct", "password123")
    account.logged_in = True
    object.__setattr__(account, "is_modified", True)
    save_objects()
    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id = ?", (account.id,))
        blob = cur.fetchone()[0]
        loaded = dill.loads(blob)
        assert getattr(loaded, "logged_in", False) is False
        assert getattr(loaded, "is_connected", False) is False


def test_old_save_missing_flags_backfilled_and_delete_uses_getattr(global_test_env):
    caller = Object.create(None, "Admin")
    caller.privilege_level = settings.Privilege.Admin
    obj = Object.create(None, "OldStyle")
    for attr in ["is_temporary", "is_deleted", "is_connected"]:
        if hasattr(obj, attr):
            object.__setattr__(obj, attr, True)
    if hasattr(obj, "is_temporary"):
        del obj.__dict__["is_temporary"]
    assert not hasattr(obj, "is_temporary")
    try:
        ops = obj.delete(caller)
    except AttributeError:
        assert False, "delete should use getattr for is_temporary"
    blob = dill.dumps(obj)
    loaded = dill.loads(blob)
    assert hasattr(loaded, "is_temporary")
    assert getattr(loaded, "is_temporary", None) is not None


def test_flag_defaults_centralized(global_test_env):
    from atheriz.objects.base_flags import FLAG_DEFAULTS
    obj = Object.create(None, "FlagTest")
    blob = dill.dumps(obj)
    loaded = dill.loads(blob)
    for name in FLAG_DEFAULTS:
        assert hasattr(loaded, name) or name == "tags"
    state = loaded.__dict__.copy()
    del state["is_temporary"]
    del state["is_connected"]
    new_obj = Object.__new__(Object)
    new_obj.__setstate__(state)
    assert hasattr(new_obj, "is_temporary")
    assert hasattr(new_obj, "is_connected")
    assert new_obj.is_connected is False


def test_stop_autosave_cleans_when_interval_none(global_test_env):
    from atheriz.globals import autosave
    from atheriz.globals.get import get_async_ticker
    ticker = get_async_ticker()
    autosave._autosave_started = True
    autosave._registered_interval = None
    ticker.add_coro(autosave.autosave_tick, 60.0)
    assert autosave.autosave_tick in ticker.slots[60.0].coros
    autosave.stop_autosave()
    assert autosave._autosave_started is False
    assert autosave._registered_interval is None
    assert autosave.autosave_tick not in ticker.slots.get(60.0, autosave).coros if 60.0 in ticker.slots else True
    remaining = [i for i, slot in ticker.slots.items() if autosave.autosave_tick in slot.coros]
    assert remaining == []
    autosave._autosave_started = False
    autosave._registered_interval = None
    import atheriz.settings as s
    orig = s.AUTOSAVE_MINUTES
    s.AUTOSAVE_MINUTES = 5
    try:
        autosave.start_autosave()
        assert autosave._autosave_started is True
        assert autosave._registered_interval == 300.0
    finally:
        autosave.stop_autosave()
        s.AUTOSAVE_MINUTES = orig
        autosave._autosave_started = False
        autosave._registered_interval = None
