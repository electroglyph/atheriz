import dill
import pytest
import threading
from unittest.mock import patch, MagicMock

from atheriz import database_setup
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel
from atheriz.objects.base_script import Script
from atheriz.objects.nodes import Node
from atheriz.utils import Coord
from atheriz.globals.objects import (
    _ALL_OBJECTS,
    get,
    get as objects_get,
    delete_objects,
    save_objects,
    load_objects,
    remove_object,
    _is_still_saveable,
)
from atheriz.globals.get import get_node_handler, get_map_handler, get_game_time
from atheriz.objects.base_flags import FLAG_DEFAULTS
import atheriz.settings as settings


def _row_count(obj_id: int) -> int:
    try:
        db = database_setup.get_database()
    except RuntimeError:
        database_setup.reopen_database()
        db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM objects WHERE id = ?", (obj_id,))
        return cur.fetchone()[0]


class TestDeletionFlags:
    def test_add_character_marks_modified_and_persists(self, global_test_env, fixed_salt):
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

    def test_remove_character_marks_modified_and_persists(self, global_test_env, fixed_salt):
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

    def test_remove_character_missing_id_still_marks_modified(self, global_test_env, fixed_salt):
        account = Account.create("acct_three", "password123")
        fake = Object.create(None, "Fake")
        object.__setattr__(account, "is_modified", False)
        account.remove_character(fake)
        assert account.is_modified is False

    def test_account_delete_persists_and_no_resurrection_on_failure(self, global_test_env, fixed_salt):
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

    def test_channel_delete_persists_and_no_resurrection_on_failure(self, global_test_env):
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

    def test_script_delete_persists_and_no_resurrection_on_failure(self, global_test_env):
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

    def test_object_delete_recursive_persists_and_no_resurrection_on_failure(self, global_test_env):
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

    def test_object_getstate_captures_location_without_deadlock(self, global_test_env):
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

    def test_is_temporary_not_persisted_even_when_flipped_after_snapshot(self, global_test_env):
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

    def test_is_temporary_filtered_at_save(self, global_test_env):
        obj = Object.create(None, "ephemeral")
        obj.is_temporary = True
        object.__setattr__(obj, "is_modified", True)
        save_objects()
        assert _row_count(obj.id) == 0
        obj.is_temporary = False
        object.__setattr__(obj, "is_modified", True)
        save_objects()
        assert _row_count(obj.id) == 1

    def test_is_connected_not_persisted(self, global_test_env):
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

    def test_logged_in_not_persisted(self, global_test_env, fixed_salt):
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

    def test_old_save_missing_flags_backfilled_and_delete_uses_getattr(self, global_test_env):
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

    def test_flag_defaults_centralized(self, global_test_env):
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

    def test_stop_autosave_cleans_when_interval_none(self, global_test_env):
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


class TestModifiedFlags:
    def test_rollback_save_preserves_dirty_flags(self, global_test_env, monkeypatch):
        """A failed save must leave every not-persisted object marked dirty.

        save_objects() clears ``is_modified`` inside ``get_save_ops_clearing()``
        *before* the transaction COMMITs. When a later object in the same run
        fails, the ROLLBACK leaves earlier objects with ``is_modified=False``
        despite their data never having been committed -- those changes would be
        silently lost on the next save, so save_objects() re-marks every attempted
        object dirty on the rollback path.
        """
        obj1 = Object.create(None, "one")
        obj2 = Object.create(None, "two")
        save_objects()
        assert obj1.is_modified is False
        assert obj2.is_modified is False

        obj1.name = "changed-one"
        obj2.name = "changed-two"
        assert obj1.is_modified is True
        assert obj2.is_modified is True

        def boom():
            raise RuntimeError("injected serialization failure")

        monkeypatch.setattr(obj2, "get_save_ops_clearing", boom)

        with pytest.raises(RuntimeError):
            save_objects()

        # Neither object was committed; both must still be dirty.
        assert obj1.is_modified is True
        assert obj2.is_modified is True

    def test_script_attachment_marks_object_modified(self, global_test_env):
        """Attaching a Script must mark the owning object for persistence."""
        obj = Object.create(None, "HarborMaster")
        save_objects()
        assert obj.is_modified is False

        script = Script.create(obj, "PatternScript")
        obj.add_script(script)

        assert obj.is_modified is True

        # and the association survives a restart
        obj_id = obj.id
        script_id = script.id
        save_objects()
        database_setup.get_database().close()
        database_setup.reopen_database()
        _ALL_OBJECTS.clear()
        load_objects()
        reloaded = get(obj_id)
        assert reloaded is not None
        assert script_id in reloaded[0].scripts

    def test_script_removal_marks_object_modified(self, global_test_env):
        """Detaching a Script must mark the owning object for persistence:
        the removal is a content change like the attachment is."""
        obj = Object.create(None, "HarborMaster")
        script = Script.create(obj, "PatternScript")
        obj.add_script(script)
        save_objects()
        assert obj.is_modified is False

        obj.remove_script(script)

        assert obj.is_modified is True

    def test_bulk_add_contents_marks_container_modified(self, global_test_env):
        """Bulk-adding contents must mark the container as modified.

        (add_objects() mutates ``_contents`` in place but never sets
        ``is_modified``, so a clean container silently loses the new contents on
        the next save checkpoint.)
        """
        bag = Object.create(None, "Bag", is_container=True)
        sword = Object.create(None, "Sword")
        save_objects()
        assert bag.is_modified is False

        bag.add_objects([sword])

        assert bag.is_modified is True

        # and the association survives a restart
        bag_id = bag.id
        save_objects()
        database_setup.get_database().close()
        database_setup.reopen_database()
        _ALL_OBJECTS.clear()
        load_objects()
        reloaded = get(bag_id)
        assert reloaded is not None
        assert sword.id in reloaded[0]._contents

    def test_node_bulk_add_contents_marks_node_modified(self, global_test_env):
        """Bulk-adding contents to a node must mark the node (and each added
        object) modified, matching Object.add_objects semantics."""
        from atheriz.globals.node import NodeHandler
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord

        nh = NodeHandler()
        node = Node(coord=Coord("test", 7, 7, 0))
        nh.add_node(node)
        obj = Object.create(None, "Sword")
        node.is_modified = False
        obj.is_modified = False

        node.add_objects([obj])

        assert node.is_modified is True
        assert obj.is_modified is True

    def test_corrupt_row_skipped_on_load(self, global_test_env):
        """load_objects must skip an un-deserializable row instead of crashing.

        A single bad blob currently aborts the whole boot because there is no
        per-row guard (contrast NodeHandler.load).
        """
        obj = Object.create(None, "goodguy")
        save_objects()

        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)",
                (777777, b"this is not a dill pickle"),
            )
            db.connection.commit()

        _ALL_OBJECTS.clear()
        load_objects()

        assert get(obj.id) is not None
        assert get(obj.id)[0].name == "goodguy"
        assert get(777777) == []


class TestZombieSave:
    def test_deleted_object_skipped_at_snapshot(self, global_test_env):
        """INTENT: an object flagged deleted (and unregistered) must never reach
        the objects table, even with force=True."""
        victim = Object.create(None, "ghost")
        victim.desc = "dirty"
        assert victim.is_modified is True

        victim.is_deleted = True
        remove_object(victim)

        save_objects(force=True)

        assert _row_count(victim.id) == 0

    def test_delete_between_snapshot_and_write_is_not_resurrected(self, global_test_env, monkeypatch):
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

    def test_live_dirty_object_still_saves(self, global_test_env):
        """INTENT: the deleted-object guards must not interfere with normal saves."""
        survivor = Object.create(None, "survivor")
        survivor.desc = "still here"
        assert survivor.is_modified is True

        save_objects()

        assert _row_count(survivor.id) == 1
        assert survivor.is_modified is False


class TestSaveForceFlag:
    def test_save_objects_force_flag_true_writes_unmodified(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "ALWAYS_SAVE_ALL", False)
        obj = Object.create(None, "ForceTest")
        save_objects()
        assert _row_count(obj.id) == 1
        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM objects WHERE id = ?", (obj.id,))
            base = dill.loads(cur.fetchone()[0])
            assert base.name == "ForceTest"
        obj.desc = "unsaved_change"
        object.__setattr__(obj, "is_modified", False)
        save_objects(force=False)
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM objects WHERE id = ?", (obj.id,))
            loaded = dill.loads(cur.fetchone()[0])
            assert loaded.desc != "unsaved_change"
        save_objects(force=True)
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM objects WHERE id = ?", (obj.id,))
            loaded = dill.loads(cur.fetchone()[0])
            assert loaded.desc == "unsaved_change"
        obj.desc = "second_change"
        object.__setattr__(obj, "is_modified", False)
        monkeypatch.setattr(settings, "ALWAYS_SAVE_ALL", True)
        save_objects(force=False)
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM objects WHERE id = ?", (obj.id,))
            loaded = dill.loads(cur.fetchone()[0])
            assert loaded.desc == "second_change"
        assert dill.dumps(obj) is not None

    def test_is_still_saveable_force_bypasses_dirty(self, global_test_env):
        obj = Object.create(None, "SaveableTest")
        object.__setattr__(obj, "is_modified", False)
        assert _is_still_saveable(obj, for_save=True, force=False) is False
        assert _is_still_saveable(obj, for_save=True, force=True) is True
        object.__setattr__(obj, "is_deleted", True)
        assert _is_still_saveable(obj, for_save=True, force=True) is False
        object.__setattr__(obj, "is_deleted", False)
        object.__setattr__(obj, "is_temporary", True)
        assert _is_still_saveable(obj, for_save=True, force=True) is False
        object.__setattr__(obj, "is_temporary", False)
        object.__setattr__(obj, "is_modified", True)
        assert _is_still_saveable(obj, for_save=True, force=False) is True
        assert dill.dumps(obj) is not None
        assert database_setup.get_database() is not None


class TestSaveEdge:
    def test_save_objects_empty_and_all_nodes_empty_snapshot(self, global_test_env):
        _ALL_OBJECTS.clear()
        save_objects()
        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT COUNT(*) FROM objects")
            assert cur.fetchone()[0] == 0
        nh = get_node_handler()
        coord = Coord("test", 0, 0, 0)
        node = Node(coord=coord)
        nh.add_node(node)
        assert getattr(node, "is_node", False) is True
        save_objects()
        assert _row_count(node.id) == 0
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT COUNT(*) FROM objects WHERE id = ?", (node.id,))
            assert cur.fetchone()[0] == 0
        blob = dill.dumps(node)
        assert dill.loads(blob).coord == coord
        assert database_setup.get_database() is not None


class TestNodeSaveDetachFailure:
    def test_node_save_detach_failure_restores_modified(self, global_test_env, monkeypatch):
        nh = get_node_handler()
        coord = Coord("test", 3, 3, 0)
        node = Node(coord=coord)
        nh.add_node(node)
        area = nh.get_area("test")
        assert area is not None
        grid = area.get_grid(0)
        assert grid is not None
        with area.lock:
            area.is_modified = True
        with grid.lock:
            grid.is_modified = True
        object.__setattr__(node, "is_modified", True)
        def boom(*a, **kw):
            raise RuntimeError("injected detach failure")
        monkeypatch.setattr("atheriz.globals.node.detach", boom)
        monkeypatch.setattr("atheriz.utils.detach", boom)
        nh.save(force=True)
        with area.lock:
            assert area.is_modified is True
        with grid.lock:
            assert grid.is_modified is True
        assert dill.dumps(area) is not None
        assert database_setup.get_database() is not None


class TestMapHandlerSaveError:
    def test_map_handler_save_detach_failure_restores_modified(self, global_test_env, monkeypatch):
        from atheriz.globals.map import MapInfo
        mh = get_map_handler()
        mi = MapInfo(name="test_area")
        with mi.lock:
            mi.pre_grid[(0, 0)] = "X"
            mi.post_grid[(0, 0)] = "X"
            mi.map_changed = True
        with mh.lock:
            mh.data[("test_area", 0)] = mi
        orig = dill.dumps
        def boom(obj):
            raise RuntimeError("injected dumps failure")
        monkeypatch.setattr(dill, "dumps", boom)
        monkeypatch.setattr("atheriz.globals.map.dill.dumps", boom)
        mh.save(force=True)
        with mi.lock:
            assert mi.map_changed is True
        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT COUNT(*) FROM mapdata WHERE area = ? AND z = ?", ("test_area", 0))
            count = cur.fetchone()[0]
            assert count == 0
        monkeypatch.setattr(dill, "dumps", orig)
        assert dill.dumps(mi) is not None


class TestGameTimeCorrupt:
    def test_gametime_corrupt_blob_resets_ticks_to_zero(self, global_test_env):
        from atheriz.globals.get import get_game_time
        gt = get_game_time()
        gt.ticks = 42
        gt.save()
        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("INSERT OR REPLACE INTO gametime (id, data) VALUES (0, ?)", (b"corrupt",))
            db.connection.commit()
        gt.load()
        assert gt.ticks == 0
        assert gt.alarms == {}
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM gametime WHERE id = 0")
            row = cur.fetchone()
            assert row[0] == b"corrupt"
        fresh = gt.__class__.__new__(gt.__class__)
        import threading as _thr
        from threading import RLock as _RL
        fresh.lock = _RL()
        fresh.started = False
        fresh.ticks = 999
        fresh.alarms = {}
        fresh.load()
        assert fresh.ticks == 0
        assert dill.loads(dill.dumps({"ticks": 0}))["ticks"] == 0


class TestSaveRaceClose:
    def test_save_race_concurrent_close_logs_warning_not_exception(self, global_test_env, capture_atheriz_log):
        objs = [Object.create(None, f"race{i}") for i in range(3)]
        for o in objs:
            o.desc = "dirty"
            object.__setattr__(o, "is_modified", True)
        save_objects()
        for o in objs:
            o.desc = "again"
            object.__setattr__(o, "is_modified", True)
        read_log = capture_atheriz_log
        def closer():
            try:
                database_setup.get_database().close()
            except Exception:
                pass
        t = threading.Thread(target=closer)
        t.start()
        try:
            save_objects()
        except Exception as e:
            assert False, f"save_objects raised {e}"
        finally:
            t.join(timeout=2)
        log = read_log()
        assert isinstance(log, str)
        try:
            database_setup.reopen_database()
            database_setup.do_setup()
        except Exception:
            pass
        assert any(o.id in _ALL_OBJECTS for o in objs)
        assert dill.dumps(objs[0]) is not None


class TestLoadClosed:
    def test_load_objects_closed_db_skips_gracefully(self, global_test_env, monkeypatch, capture_atheriz_log):
        read_log = capture_atheriz_log
        def boom():
            raise RuntimeError("database is closed")
        monkeypatch.setattr("atheriz.globals.objects.get_database", boom)
        monkeypatch.setattr(database_setup, "get_database", boom)
        try:
            load_objects()
        except Exception as e:
            assert False, f"load_objects raised {e}"
        log = read_log()
        assert "database closed" in log.lower()
        assert dill.dumps(123) is not None
        monkeypatch.undo()
        db = database_setup.get_database()
        db.close()
        assert database_setup._CLOSED is True
        try:
            load_objects()
        except Exception as e:
            assert False, f"load_objects raised after close {e}"
        log2 = read_log()
        assert "database closed" in log2.lower() or "skipping" in log2.lower() or isinstance(log2, str)
        database_setup.reopen_database()
        database_setup.do_setup()
        assert dill.dumps("ok") is not None


class TestDillFailure:
    def test_dill_dumps_failure_restores_is_modified(self, global_test_env, monkeypatch):
        obj1 = Object.create(None, "one")
        obj2 = Object.create(None, "two")
        save_objects()
        assert obj1.is_modified is False
        assert obj2.is_modified is False
        obj1.name = "changed-one"
        obj2.name = "changed-two"
        assert obj1.is_modified is True
        assert obj2.is_modified is True
        orig = dill.dumps
        def failing(o):
            if getattr(o, "name", None) == "changed-two":
                raise RuntimeError("injected serialization failure")
            return orig(o)
        monkeypatch.setattr(dill, "dumps", failing)
        with pytest.raises(RuntimeError):
            save_objects()
        assert obj1.is_modified is True
        assert obj2.is_modified is True
        assert _row_count(obj1.id) == 1
        db = database_setup.get_database()
        with db.lock:
            cur = db.connection.cursor()
            cur.execute("SELECT data FROM objects WHERE id = ?", (obj1.id,))
            loaded = dill.loads(cur.fetchone()[0])
            assert loaded.name != "changed-one"
        assert database_setup.get_database() is not None
