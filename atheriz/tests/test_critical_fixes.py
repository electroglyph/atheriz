"""Regression tests for critical correctness fixes (behavior-named)."""
from __future__ import annotations
import sys
import threading
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch
import pytest


# ------------------------------------------------------------------ C1
def test_recursive_delete_stops_at_depth_limit(global_test_env, monkeypatch):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.globals.objects import get
    monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 5)
    admin = Object.create(None, "admin")
    admin.privilege_level = settings.Privilege.Admin
    root = Object.create(None, "root")
    root.is_container = True
    prev = root
    chain = []
    for i in range(10):
        child = Object.create(None, f"c{i}")
        child.is_container = True
        child.move_to(prev)
        chain.append(child)
        prev = child
    deepest = chain[-1]
    root.delete(admin, recursive=True)
    assert not get(root.id), "root should be deleted"
    assert get(deepest.id), "deep objects beyond limit should survive truncation"
    assert get(chain[6].id), "objects beyond MAX_SEARCH_DEPTH should remain"


def test_recursive_delete_truncates_at_exact_boundary(global_test_env, monkeypatch):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.globals.objects import get
    monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 5)
    admin = Object.create(None, "admin2")
    admin.privilege_level = settings.Privilege.Admin
    root = Object.create(None, "root2")
    root.is_container = True
    prev = root
    chain = []
    for i in range(7):
        c = Object.create(None, f"b{i}")
        c.is_container = True
        c.move_to(prev)
        chain.append(c)
        prev = c
    # depth: root0, b0=1,b1=2,b2=3,b3=4,b4=5,b5=6,b6=7
    # MAX 5 -> push only depth<5, so survivors are b4..b6
    root.delete(admin, recursive=True)
    for i in range(4):
        assert not get(chain[i].id), f"b{i} depth {i+1}<5 should be deleted"
    for i in range(4, 7):
        assert get(chain[i].id), f"b{i} depth {i+1}>=5 should survive"


def test_recursive_delete_non_recursive_leaves_children(global_test_env, monkeypatch):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.globals.objects import get
    monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 100)
    admin = Object.create(None, "admin3")
    admin.privilege_level = settings.Privilege.Admin
    root = Object.create(None, "root3")
    root.is_container = True
    child = Object.create(None, "child3")
    child.is_container = True
    grand = Object.create(None, "grand3")
    grand.is_container = True
    grand.move_to(child)
    child.move_to(root)
    root.delete(admin, recursive=False)
    assert not get(root.id)
    assert get(child.id), "non-recursive should leave direct child"
    assert get(grand.id), "non-recursive should leave grandchild"


# ------------------------------------------------------------------ C2
def test_subscribe_and_channel_delete_do_not_deadlock(global_test_env):
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel
    obj = Object.create(None, "player")
    chan = Channel.create("testchan")
    barrier = threading.Barrier(2)
    errors = []

    def subscriber():
        try:
            barrier.wait(timeout=2)
            for _ in range(50):
                obj.subscribe(chan)
                obj.unsubscribe(chan)
        except Exception as e:
            errors.append(e)

    def deleter():
        try:
            barrier.wait(timeout=2)
            for _ in range(50):
                if chan.is_deleted:
                    break
                try:
                    chan.delete(None)
                except Exception as e:
                    errors.append(e)
                if chan.is_deleted:
                    break
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=subscriber)
    t2 = threading.Thread(target=deleter)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not t1.is_alive(), "subscribe thread deadlocked"
    assert not t2.is_alive(), "delete thread deadlocked"
    assert not errors, f"errors in concurrent subscribe/delete: {errors}"


def test_subscribe_normal_operation_adds_state(global_test_env):
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel
    obj = Object.create(None, "player2")
    chan = Channel.create("chan2")
    obj.subscribe(chan)
    assert chan.id in obj.channels
    assert obj.id in chan.listeners
    # idempotent
    obj.subscribe(chan)
    assert obj.channels.count(chan.id) == 1
    obj.unsubscribe(chan)
    assert chan.id not in obj.channels
    assert obj.id not in chan.listeners


def test_subscribe_state_consistency_under_concurrent_race(global_test_env):
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel
    objs = [Object.create(None, f"p{i}") for i in range(3)]
    chan = Channel.create("racechan")
    barrier = threading.Barrier(len(objs))
    errors = []

    def worker(o):
        try:
            barrier.wait(timeout=2)
            for _ in range(30):
                o.subscribe(chan)
                o.unsubscribe(chan)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(o,)) for o in objs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert not errors
    for o in objs:
        assert chan.id not in o.channels or o.id in chan.listeners
        if o.id not in chan.listeners:
            assert chan.id not in o.channels


# ------------------------------------------------------------------ C3
def test_connection_without_owning_loop_raises(global_test_env):
    from atheriz.network.connection import BaseConnection
    conn = BaseConnection.__new__(BaseConnection)
    import threading as _th
    from collections import deque
    conn.session_id = "x"
    from atheriz.objects.session import Session
    conn.session = Session(connection=conn)
    conn.loop = None
    conn.thread_id = _th.get_ident()
    conn.lock = _th.RLock()
    conn.failed_login_attempts = 0
    conn._input_queue = deque()
    conn._input_running = False
    conn._last_input_busy = 0.0
    conn._disconnected = False
    with pytest.raises(RuntimeError, match="owning event loop"):
        conn._resolve_loop()


def test_connection_with_captured_loop_returns_it(global_test_env, running_loop):
    from atheriz.network.connection import BaseConnection
    loop = running_loop
    async def _make():
        c = BaseConnection(session_id="s2")
        return c
    fut = asyncio.run_coroutine_threadsafe(_make(), loop)
    conn = fut.result(timeout=2)
    assert conn._resolve_loop() is loop


def test_connection_cross_thread_resolves_to_owning_loop(global_test_env, running_loop):
    from atheriz.network.connection import BaseConnection
    loop = running_loop
    async def _make():
        c = BaseConnection(session_id="s3")
        return c
    conn = asyncio.run_coroutine_threadsafe(_make(), loop).result(timeout=2)
    result = []
    def from_worker():
        result.append(conn._resolve_loop())
    t = threading.Thread(target=from_worker)
    t.start()
    t.join(timeout=2)
    assert result[0] is loop
    # off-loop without captured loop must raise, not return threadpool loop
    from collections import deque
    import threading as _th
    from atheriz.objects.session import Session
    orphan = BaseConnection.__new__(BaseConnection)
    orphan.session_id = "orphan"
    orphan.session = Session(connection=orphan)
    orphan.loop = None
    orphan.thread_id = _th.get_ident()
    orphan.lock = _th.RLock()
    orphan.failed_login_attempts = 0
    orphan._input_queue = deque()
    orphan._input_running = False
    orphan._last_input_busy = 0.0
    orphan._disconnected = False
    errs = []
    def try_orphan():
        try:
            orphan._resolve_loop()
        except RuntimeError as e:
            errs.append(str(e))
    t2 = threading.Thread(target=try_orphan)
    t2.start()
    t2.join(timeout=2)
    assert errs and "owning event loop" in errs[0]


# ------------------------------------------------------------------ C4
def test_pid_file_acquire_never_uses_truncate(global_test_env):
    import atheriz.atheriz as az
    import pathlib
    src = pathlib.Path(az.__file__).read_text(encoding="utf-8")
    assert 'open(pid_file, "w"' not in src, "PID file must never be opened with truncating 'w'"
    assert src.count('open(pid_file, "x"') >= 3, "PID acquire should use exclusive 'x' with retries"


def test_pid_file_acquire_retries_without_truncate_on_race(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from pathlib import Path
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    pid_file.write_text("999999", encoding="utf-8")
    monkeypatch.setattr(az, "_pid_is_server_process", lambda pid: False)
    calls: list[str] = []
    real_open = open
    def fake_open(path, mode="r", *a, **kw):
        if isinstance(path, Path) and path.name == "server.pid":
            calls.append(mode)
            if mode == "w":
                raise AssertionError("should not open with w")
        return real_open(path, mode, *a, **kw)
    with patch("builtins.open", side_effect=fake_open):
        try:
            with open(pid_file, "x", encoding="utf-8") as f:
                f.write("1")
        except FileExistsError:
            pid_file.unlink(missing_ok=True)
            with open(pid_file, "x", encoding="utf-8") as f:
                f.write("1")
    assert "w" not in calls
    assert "x" in calls


# ------------------------------------------------------------------ C5
def test_hot_reload_preserves_live_object_state(global_test_env):
    from atheriz.objects.base_obj import Object
    from atheriz.reloader import _apply_patch
    from atheriz.globals.objects import _ALL_OBJECTS
    obj = Object.create(None, "patchme")
    obj.damage = 42  # type: ignore
    orig_id = obj.id
    orig_contents = set(getattr(obj, "_contents", set()))
    count_before = len(_ALL_OBJECTS)
    class V2(Object):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.new_attr = 999
    _apply_patch(obj, V2)
    assert obj.__class__ is V2
    assert obj.id == orig_id
    assert getattr(obj, "damage", None) == 42
    assert len(_ALL_OBJECTS) == count_before
    assert set(getattr(obj, "_contents", set())) == orig_contents


def test_hot_reload_preserves_node_coord_and_contents(global_test_env):
    from atheriz.objects.nodes import Node, Coord
    from atheriz.reloader import _apply_patch
    from atheriz.objects.base_obj import Object
    from atheriz.globals.objects import _ALL_OBJECTS, get
    coord = Coord(1, 2, 0, "testarea")
    node = Node(coord=coord, desc="orig")
    occ = Object.create(None, "occ")
    occ.move_to(node)
    orig_coord = node.coord
    orig_desc = node.desc
    orig_contents = set(node._contents)
    orig_id = node.id
    orig_lock = node.lock
    count_before = len(_ALL_OBJECTS)
    class V2(Node):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.new_field = "new"
        def extra_method(self):
            return 1
    _apply_patch(node, V2)
    assert node.__class__ is V2
    assert node.id == orig_id
    assert node.coord == orig_coord
    assert node.desc == orig_desc
    assert set(node._contents) == orig_contents
    assert len(_ALL_OBJECTS) == count_before
    assert get(occ.id)[0] is occ
    assert occ.location is node
    assert hasattr(node, "lock")
    assert node.extra_method() == 1


# ------------------------------------------------------------------ C6/C7
def test_set_rejects_direct_location_assignment(global_test_env):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.commands.loggedin.set import SetCommand
    caller = Object.create(None, "builder")
    caller.privilege_level = settings.Privilege.Builder
    msgs = []
    caller.msg = lambda *a, **k: msgs.append(" ".join(str(x) for x in a))
    from atheriz.objects.session import Session
    caller.session = Session(connection=None)
    target = Object.create(None, "victim")
    dest = Object.create(None, "dest")
    cmd = SetCommand()
    args = SimpleNamespace(target=f"#{target.id}", attribute="location", value=str(dest.id))
    msgs.clear()
    cmd.run(caller, args)
    assert any("cannot be set directly" in m.lower() or "protected" in m.lower() for m in msgs), msgs
    assert getattr(target, "location", None) != dest.id
    assert getattr(target, "location", None) != dest


def test_set_rejects_direct_home_assignment(global_test_env):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.commands.loggedin.set import SetCommand
    caller = Object.create(None, "builder2")
    caller.privilege_level = settings.Privilege.Admin
    msgs = []
    caller.msg = lambda *a, **k: msgs.append(" ".join(str(x) for x in a))
    from atheriz.objects.session import Session
    caller.session = Session(connection=None)
    target = Object.create(None, "victim2")
    dest = Object.create(None, "dest2")
    cmd = SetCommand()
    args = SimpleNamespace(target=f"#{target.id}", attribute="home", value=str(dest.id))
    cmd.run(caller, args)
    assert any("cannot be set directly" in m.lower() or "protected" in m.lower() for m in msgs)


def test_set_rejects_group_channel_and_contents(global_test_env):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.commands.loggedin.set import SetCommand
    caller = Object.create(None, "builder_gc")
    caller.privilege_level = settings.Privilege.Builder
    msgs = []
    caller.msg = lambda *a, **k: msgs.append(" ".join(str(x) for x in a))
    from atheriz.objects.session import Session
    caller.session = Session(connection=None)
    target = Object.create(None, "victim_gc")
    for attr in ("_contents", "group_channel", "contents"):
        msgs.clear()
        cmd = SetCommand()
        args = SimpleNamespace(target=f"#{target.id}", attribute=attr, value="123")
        cmd.run(caller, args)
        assert any("cannot be set directly" in m.lower() or "protected" in m.lower() for m in msgs), f"{attr} should be blocked"


def test_set_allows_valid_attribute(global_test_env):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.commands.loggedin.set import SetCommand
    caller = Object.create(None, "builder_ok")
    caller.privilege_level = settings.Privilege.Builder
    caller.msg = lambda *a, **k: None
    from atheriz.objects.session import Session
    caller.session = Session(connection=None)
    target = Object.create(None, "victim_ok")
    cmd = SetCommand()
    args = SimpleNamespace(target=f"#{target.id}", attribute="desc", value="'hello'")
    cmd.run(caller, args)
    assert target.desc == "hello"


def test_unset_rejects_location_removal(global_test_env):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.commands.loggedin.set import UnsetCommand
    caller = Object.create(None, "builder3")
    caller.privilege_level = settings.Privilege.Builder
    msgs = []
    caller.msg = lambda *a, **k: msgs.append(" ".join(str(x) for x in a))
    target = Object.create(None, "victim3")
    assert hasattr(target, "location")
    cmd = UnsetCommand()
    args = SimpleNamespace(target=f"#{target.id}", attribute="location")
    cmd.run(caller, args)
    assert any("cannot be removed" in m.lower() or "protected" in m.lower() for m in msgs)
    assert hasattr(target, "location")


def test_unset_rejects_protected_and_allows_valid(global_test_env):
    from atheriz import settings
    from atheriz.objects.base_obj import Object
    from atheriz.commands.loggedin.set import UnsetCommand
    caller = Object.create(None, "builder_u2")
    caller.privilege_level = settings.Privilege.Builder
    msgs = []
    caller.msg = lambda *a, **k: msgs.append(" ".join(str(x) for x in a))
    target = Object.create(None, "victim_u2")
    target.custom = "x"
    cmd = UnsetCommand()
    args = SimpleNamespace(target=f"#{target.id}", attribute="custom")
    cmd.run(caller, args)
    assert not hasattr(target, "custom")
    # protected home should remain
    target.home = 123
    msgs.clear()
    args2 = SimpleNamespace(target=f"#{target.id}", attribute="home")
    cmd.run(caller, args2)
    assert hasattr(target, "home")


# ------------------------------------------------------------------ C9
def test_stop_server_fallback_ignores_established_connection(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    if pid_file.exists():
        pid_file.unlink()
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)
    proc = MagicMock()
    proc.pid = 999
    proc.name.return_value = "python"
    proc.terminate = MagicMock()
    conn = SimpleNamespace(pid=999, status="ESTABLISHED", laddr=SimpleNamespace(port=settings.WEBSERVER_PORT))
    fake = MagicMock()
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    fake.Process.return_value = proc
    fake.net_connections.return_value = [conn]
    monkeypatch.setitem(sys.modules, "psutil", fake)
    az.stop_server()
    proc.terminate.assert_not_called()


def test_stop_server_fallback_ignores_non_python_listener(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    if pid_file.exists():
        pid_file.unlink()
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)
    proc = MagicMock()
    proc.pid = 111
    proc.name.return_value = "nginx"
    proc.terminate = MagicMock()
    conn = SimpleNamespace(pid=111, status="LISTEN", laddr=SimpleNamespace(port=settings.WEBSERVER_PORT))
    fake = MagicMock()
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    fake.Process.return_value = proc
    fake.net_connections.return_value = [conn]
    monkeypatch.setitem(sys.modules, "psutil", fake)
    az.stop_server()
    proc.terminate.assert_not_called()


def test_stop_server_fallback_kills_verified_python_listener(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    if pid_file.exists():
        pid_file.unlink()
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)
    proc = MagicMock()
    proc.pid = 12345
    proc.name.return_value = "python"
    proc.is_running.return_value = False
    proc.wait = MagicMock(return_value=None)
    proc.terminate = MagicMock(return_value=None)
    listener = SimpleNamespace(pid=12345, status="LISTEN", laddr=SimpleNamespace(port=settings.WEBSERVER_PORT))
    fake = MagicMock()
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    fake.Process.return_value = proc
    fake.net_connections.return_value = [listener]
    monkeypatch.setitem(sys.modules, "psutil", fake)
    az.stop_server()
    proc.terminate.assert_called_once()


def test_stop_server_fallback_mixed_connections_skips_established(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    if pid_file.exists():
        pid_file.unlink()
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)
    proc_bad = MagicMock()
    proc_bad.pid = 100
    proc_bad.name.return_value = "python"
    proc_bad.terminate = MagicMock()
    proc_good = MagicMock()
    proc_good.pid = 200
    proc_good.name.return_value = "python"
    proc_good.is_running.return_value = False
    proc_good.wait = MagicMock(return_value=None)
    proc_good.terminate = MagicMock()
    est = SimpleNamespace(pid=100, status="ESTABLISHED", laddr=SimpleNamespace(port=settings.WEBSERVER_PORT))
    lst = SimpleNamespace(pid=200, status="LISTEN", laddr=SimpleNamespace(port=settings.WEBSERVER_PORT))
    fake = MagicMock()
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    def fake_process(pid):
        return proc_good if pid == 200 else proc_bad
    fake.Process.side_effect = fake_process
    fake.net_connections.return_value = [est, lst]
    monkeypatch.setitem(sys.modules, "psutil", fake)
    az.stop_server()
    proc_bad.terminate.assert_not_called()
    proc_good.terminate.assert_called_once()


def test_stop_server_fallback_double_verify_failure_does_not_kill(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    if pid_file.exists():
        pid_file.unlink()
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)
    proc = MagicMock()
    proc.pid = 300
    proc.name.return_value = "python"
    proc.terminate = MagicMock()
    listener = SimpleNamespace(pid=300, status="LISTEN", laddr=SimpleNamespace(port=settings.WEBSERVER_PORT))
    fake = MagicMock()
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    fake.Process.return_value = proc
    fake.net_connections.return_value = [listener]
    monkeypatch.setitem(sys.modules, "psutil", fake)
    monkeypatch.setattr(az, "_process_listening_by_port", lambda p, port: False)
    az.stop_server()
    proc.terminate.assert_not_called()


def test_stop_server_fallback_handles_psutil_error(global_test_env, monkeypatch):
    import atheriz.atheriz as az
    from atheriz import settings
    pid_file = Path(settings.SAVE_PATH) / "server.pid"
    if pid_file.exists():
        pid_file.unlink()
    monkeypatch.setattr(az, "request_internal_shutdown", lambda port=None: False)
    fake = MagicMock()
    fake.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake.AccessDenied = type("AccessDenied", (Exception,), {})
    fake.ZombieProcess = type("ZombieProcess", (Exception,), {})
    fake.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
    fake.net_connections.side_effect = Exception("boom")
    monkeypatch.setitem(sys.modules, "psutil", fake)
    az.stop_server()
