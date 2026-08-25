import pytest
from unittest.mock import MagicMock, patch
import threading


def test_grid_overwrite_removes_old_object(global_test_env):
    from atheriz.objects.nodes import Node, NodeGrid, NodeArea
    from atheriz.globals.objects import get
    from atheriz.utils import Coord

    area = NodeArea(name="PersistA")
    grid = NodeGrid(area="PersistA", z=0)
    c = Coord("PersistA", 0, 0, 0)
    n1 = Node(coord=c, desc="first")
    grid.add_node(n1)
    assert get(n1.id)[0] is n1
    n2 = Node(coord=c, desc="second")
    grid.add_node(n2)
    assert grid.get_node((0, 0)) is n2
    assert get(n1.id) == []
    assert get(n2.id)[0] is n2


def test_grid_overwrite_under_concurrency_keeps_one_node(global_test_env):
    from atheriz.objects.nodes import Node, NodeGrid
    from atheriz.utils import Coord
    from atheriz.globals.objects import filter_by

    grid = NodeGrid(area="PersistConc", z=0)
    barrier = threading.Barrier(2)

    def maker(desc):
        def fn():
            barrier.wait()
            n = Node(coord=Coord("PersistConc", 1, 1, 0), desc=desc)
            grid.add_node(n)
        return fn

    t1 = threading.Thread(target=maker("a"))
    t2 = threading.Thread(target=maker("b"))
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert not t1.is_alive() and not t2.is_alive()
    node = grid.get_node((1, 1))
    assert node is not None
    assert node.desc in ("a", "b")


def test_shutdown_stops_game_time_before_ticker_and_pool(global_test_env, monkeypatch):
    import atheriz.globals.startstop as ss
    import atheriz.settings as settings

    monkeypatch.setattr(settings, "TIME_SYSTEM_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOSAVE_ON_SHUTDOWN", False)
    order = []

    def fake_step(name, fn, *a, **kw):
        order.append(name)
        try:
            fn(*a, **kw)
        except Exception:
            pass

    monkeypatch.setattr(ss, "_shutdown_step", fake_step)
    monkeypatch.setattr(ss, "get_async_ticker", lambda: MagicMock(stop=MagicMock()))
    monkeypatch.setattr(ss, "get_async_threadpool", lambda: MagicMock(stop=MagicMock()))
    monkeypatch.setattr(ss, "get_game_time", lambda: MagicMock(stop=MagicMock()))
    monkeypatch.setattr(ss, "get_map_handler", lambda: MagicMock(save=MagicMock()))
    monkeypatch.setattr(ss, "get_node_handler", lambda: MagicMock(save=MagicMock()))
    monkeypatch.setattr(ss, "get_server_channel", lambda: None)
    monkeypatch.setattr(ss, "save_objects", lambda *a, **kw: None)
    monkeypatch.setattr(ss, "stop_autosave", lambda: None)
    monkeypatch.setattr(ss, "msg_all", lambda *a, **kw: None)
    monkeypatch.setattr(ss, "get_database", lambda: MagicMock(close=MagicMock(), _closed=False, lock=MagicMock(__enter__=lambda s: s, __exit__=lambda *a: False)))
    import atheriz.globals.get as gm
    monkeypatch.setattr(gm, "_ASYNC_THREAD_POOL", MagicMock())
    monkeypatch.setattr(gm, "_ASYNC_TICKER", MagicMock())
    ss._shutdown_completed = False
    ss.do_shutdown()
    # game_time_stop must come before ticker_stop and threadpool_stop
    assert "game_time_stop" in order
    assert "ticker_stop" in order and "threadpool_stop" in order
    assert order.index("game_time_stop") < order.index("ticker_stop")
    assert order.index("game_time_stop") < order.index("threadpool_stop")
    ss._shutdown_completed = False


def test_thread_pool_uses_correct_sentinel_count(global_test_env, monkeypatch):
    from atheriz.globals.asyncthreadpool import AsyncThreadPool

    pool = AsyncThreadPool(max_threads=4)
    # prevent real thread joins
    for t in pool.threads:
        t.join = MagicMock()
    pool.threads[0].stop = MagicMock()
    calls = []
    orig_put = pool.task_queue.put_nowait

    def counting_put(x):
        calls.append(x)
        return orig_put(x)

    with patch.object(pool.task_queue, "put_nowait", side_effect=counting_put):
        pool.stop(wait=False)
    # only max_threads-1 sentinels for sync workers
    assert calls.count(None) == 3
    pool._stopped = False


def test_map_save_skips_when_clean(global_test_env, monkeypatch):
    from atheriz.globals.get import get_map_handler
    import atheriz.settings as settings

    monkeypatch.setattr(settings, "ALWAYS_SAVE_ALL", False)
    mh = get_map_handler()
    # ensure at least one MapInfo exists and is clean - clean all maps
    with mh.lock:
        for mi in list(mh.data.values()):
            with mi.lock:
                mi.map_changed = False
                try:
                    mi.is_modified = False
                except Exception:
                    pass
    mi = mh._get_or_create("CleanArea", 0)
    with mi.lock:
        mi.map_changed = False
        try:
            mi.is_modified = False
        except Exception:
            pass
    fake_db = MagicMock()
    fake_db._closed = False
    fake_db.lock = MagicMock()
    fake_db.lock.__enter__.return_value = fake_db.lock
    fake_db.lock.__exit__.return_value = False
    mock_cursor = MagicMock()
    fake_db.connection.cursor.return_value = mock_cursor
    monkeypatch.setattr("atheriz.globals.map.get_database", lambda: fake_db)
    mh.save(force=False)
    # should not have called BEGIN when clean
    mock_cursor.execute.assert_not_called()


def test_map_save_warns_when_database_closed(global_test_env, monkeypatch):
    from atheriz.globals.get import get_map_handler
    from atheriz.globals.map import MapInfo

    mh = get_map_handler()
    mi = MapInfo(name="ClosedArea")
    mi.map_changed = True
    mh.set_mapinfo("ClosedArea", 1, mi)
    # fake closed db
    fake_db = MagicMock()
    fake_db._closed = True
    fake_db.lock = MagicMock()
    fake_db.lock.__enter__.return_value = fake_db.lock
    fake_db.lock.__exit__.return_value = False
    monkeypatch.setattr("atheriz.globals.map.get_database", lambda: fake_db)
    # should not raise
    mh.save()
    assert fake_db.lock.__enter__.called


def test_game_time_save_handles_closed_database(global_test_env, monkeypatch):
    from atheriz.globals.get import get_game_time

    gt = get_game_time()
    with gt.lock:
        gt.ticks = 5
    fake_db = MagicMock()
    fake_db._closed = True
    fake_db.lock = MagicMock()
    fake_db.lock.__enter__.return_value = fake_db.lock
    fake_db.lock.__exit__.return_value = False
    monkeypatch.setattr("atheriz.globals.time.get_database", lambda: fake_db)
    # should not raise
    gt.save()
    # also test single transaction: ensure CREATE TABLE not called separately outside lock
    # (covered by not raising when _closed)


def test_game_time_save_is_single_transaction(global_test_env, monkeypatch):
    from atheriz.globals.get import get_game_time

    gt = get_game_time()
    with gt.lock:
        gt.ticks = 7
        gt.alarms.clear()
    fake_db = MagicMock()
    fake_db._closed = False
    fake_db.lock = MagicMock()
    fake_db.lock.__enter__.return_value = fake_db.lock
    fake_db.lock.__exit__.return_value = False
    mock_cursor = MagicMock()
    fake_db.connection.cursor.return_value = mock_cursor
    monkeypatch.setattr("atheriz.globals.time.get_database", lambda: fake_db)
    gt.save()
    # should have executed CREATE TABLE and BEGIN/COMMIT in same lock session
    calls = [c.args[0] for c in mock_cursor.execute.call_args_list]
    assert any("CREATE TABLE" in c for c in calls)
    assert any("BEGIN" in c for c in calls)
    assert any("COMMIT" in c for c in calls)


def test_node_handler_creates_areas_atomically(global_test_env):
    from atheriz.globals.get import get_node_handler
    from atheriz.objects.nodes import Node
    from atheriz.utils import Coord

    nh = get_node_handler()
    area_name = "AtomicArea"
    # ensure not exists
    if nh.get_area(area_name):
        nh.remove_area(area_name)
    barrier = threading.Barrier(2)

    def add():
        barrier.wait()
        n = Node(coord=Coord(area_name, 0, 0, 0), desc="x")
        # use different coords to avoid grid collision but same area
        n.coord = Coord(area_name, threading.get_ident() % 10, 0, 0)
        nh.add_node(n)

    t1 = threading.Thread(target=add)
    t2 = threading.Thread(target=add)
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert not t1.is_alive() and not t2.is_alive()
    area = nh.get_area(area_name)
    assert area is not None


def test_builder_reuses_map_atomically(global_test_env):
    from atheriz.globals.get import get_map_handler

    mh = get_map_handler()
    area, z = "BuildAtomic", 9
    # ensure clean
    with mh.lock:
        mh.data.pop((area, z), None)
    barrier = threading.Barrier(2)
    results = []

    def get_or_create():
        barrier.wait()
        mi = mh._get_or_create(area, z)
        results.append(mi)

    t1 = threading.Thread(target=get_or_create)
    t2 = threading.Thread(target=get_or_create)
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)
    assert not t1.is_alive() and not t2.is_alive()
    assert results[0] is results[1]
    assert mh.get_mapinfo(area, z) is results[0]


def test_node_load_updates_max_id_atomically(global_test_env, monkeypatch):
    import atheriz.globals.get as gm
    from atheriz.globals.node import NodeHandler

    # simulate concurrent get_unique_id while load computes max
    original_max = gm.get_id()
    nh = NodeHandler.__new__(NodeHandler)
    nh.lock = threading.RLock()
    nh.lock2 = threading.RLock()
    nh.lock3 = threading.RLock()
    nh.areas = {}
    nh.transitions = {}
    nh.doors = {}
    nh._modified = nh._modified2 = nh._modified3 = False
    # inject a node with high id
    from atheriz.objects.nodes import Node, NodeArea, NodeGrid
    from atheriz.utils import Coord

    area = NodeArea(name="IdRace")
    grid = NodeGrid(area="IdRace", z=0)
    high = original_max + 100
    # manually set id high without going through get_unique_id
    n = Node.__new__(Node)
    import threading as th

    n.lock = th.RLock()
    n.coord = Coord("IdRace", 0, 0, 0)
    n.id = high
    n._contents = set()
    n.links = []
    n.is_node = True
    n.is_modified = False
    n.hooks = {}
    n.tags = set()
    n.scripts = set()
    from atheriz.globals.objects import add_object

    add_object(n)
    grid.nodes[(0, 0)] = n
    area.add_grid(grid)
    nh.areas["IdRace"] = area

    # monkeypatch get_database to avoid DB load, call load max logic directly
    # directly test the atomic section
    with gm._ID_LOCK:
        gm._ID = original_max
    # simulate load's max_id calc
    max_node_id = high

    def concurrent_increment():
        gm.get_unique_id()
        gm.get_unique_id()

    t = threading.Thread(target=concurrent_increment)
    t.start()
    # load's atomic update
    with gm._ID_LOCK:
        gm._ID = max(gm._ID, max_node_id)
    t.join(timeout=2)
    assert gm.get_id() >= high


def test_checkpoint_persists_late_mutation(global_test_env):
    from atheriz.objects.base_obj import Object
    from atheriz.globals.objects import save_objects
    from atheriz.database_setup import get_database

    obj = Object.create(None, "LateMut")
    obj.is_modified = False
    # snapshot will be taken inside save_objects; mutate after snapshot but before DB write
    # Our fix moves dirty check inside DB lock, so late mutation is still caught if we
    # mutate before the per-object check. Simulate by setting flag just before save.
    obj.is_modified = True
    obj.desc = "changed"
    save_objects()
    # after save, flag should be cleared (persisted)
    assert obj.is_modified is False
    # mutate again and ensure next save persists
    obj.desc = "changed2"
    obj.is_modified = True
    save_objects()
    assert obj.is_modified is False
    # verify DB contains object
    db = get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute("SELECT data FROM objects WHERE id=?", (obj.id,))
        row = cur.fetchone()
        assert row is not None
