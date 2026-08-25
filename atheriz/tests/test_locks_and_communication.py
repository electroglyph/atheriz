import asyncio
import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from atheriz.menu import Choice, MenuEngine
from atheriz.objects.session import Session
from atheriz.objects.base_door import Door
from atheriz.objects.nodes import Node
from atheriz.utils import Coord
from atheriz.commands.loggedin.mapedit import DrawCommand
from atheriz.commands.loggedin.channel import ChannelCommand
from atheriz.objects.base_channel import Channel


def _menu_node(ctx):
    return "Hello", [Choice(key="1", desc="One", goto=None)]


def test_menu_display_uses_crlf_for_telnet():
    engine = MenuEngine("player", _menu_node)
    display = engine.get_display()
    assert "\r\n" in display
    assert display.count("\r\n") >= 1
    # interior lines use CRLF not bare LF alone
    # split by CRLF should reconstruct lines
    parts = display.split("\r\n")
    assert len(parts) >= 2


def _make_builder(name: str):
    from atheriz.objects.base_obj import Object
    import atheriz.settings as settings

    obj = Object.create(None, name)
    obj.privilege_level = settings.Privilege.Builder
    return obj


def test_mapedit_handles_missing_session_gracefully(global_test_env):
    caller = _make_builder("Builder")
    caller.session = None
    node = Node(coord=Coord("TestArea", 0, 0, 0))
    from atheriz.globals.get import get_node_handler

    nh = get_node_handler()
    nh.add_node(node)
    caller.location = node
    msgs = []
    caller.msg = lambda *a, **kw: msgs.append(" ".join(str(x) for x in a))
    cmd = DrawCommand()
    cmd.run(caller, MagicMock())
    assert any("No active connection" in m for m in msgs)


def test_mapedit_handles_none_connection_gracefully(global_test_env):
    caller = _make_builder("Builder2")
    sess = Session(connection=None)
    caller.session = sess
    node = Node(coord=Coord("TestArea", 1, 0, 0))
    from atheriz.globals.get import get_node_handler

    nh = get_node_handler()
    nh.add_node(node)
    caller.location = node
    caller.session.connection = None
    msgs = []
    caller.msg = lambda *a, **kw: msgs.append(" ".join(str(x) for x in a))
    cmd = DrawCommand()
    cmd.run(caller, MagicMock())
    assert any("No active connection" in m for m in msgs)


def test_channel_cache_skips_deleted_entry(global_test_env):
    chan = Channel.create("CacheTestChan")
    chan.desc = "desc"
    cmd = ChannelCommand()
    name = chan.name.lower()
    cmd._channel_cache[name] = chan
    chan.is_deleted = True  # type: ignore[attr-defined]
    with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[]):
        caller = MagicMock()
        caller.msg = MagicMock()
        args = MagicMock()
        args.channel = chan.name
        args.list = False
        args.unsubscribe = False
        args.subscribe = False
        args.replay = False
        args.message = None
        cmd.run(caller, args)
        assert name not in cmd._channel_cache
        caller.msg.assert_called()
        assert "not found" in str(caller.msg.call_args[0][0]).lower()
    chan.is_deleted = False


def test_channel_cache_revalidates_name_mismatch(global_test_env):
    chan = Channel.create("ValidChan")
    chan.desc = "desc"
    cmd = ChannelCommand()
    name = chan.name.lower()
    other = Channel.create("OtherChan")
    other.desc = "desc2"
    cmd._channel_cache[name] = other
    with patch("atheriz.commands.loggedin.channel.filter_by", return_value=[chan]) as mock_filter:
        caller = MagicMock()
        caller.msg = MagicMock()
        caller.unsubscribe = MagicMock()
        args = MagicMock()
        args.channel = chan.name
        args.list = False
        args.unsubscribe = True
        args.subscribe = False
        args.replay = False
        args.message = None
        cmd.run(caller, args)
        mock_filter.assert_called()
        assert cmd._channel_cache.get(name) is chan


def test_door_broadcast_does_not_hold_lock(global_test_env):
    from atheriz.objects.base_obj import Object
    from unittest.mock import MagicMock

    door = Door.create(
        from_coord=Coord("TestArea", 0, 0, 0),
        from_exit="n",
        to_coord=Coord("TestArea", 0, 1, 0),
        to_exit="s",
        symbol_coord=(0, 0),
        closed_symbol="C",
        open_symbol="O",
        closed=True,
        locked=False,
    )
    from_node = Node(coord=Coord("TestArea", 0, 0, 0))
    to_node = Node(coord=Coord("TestArea", 0, 1, 0))
    # register nodes via handler
    from atheriz.globals.get import get_node_handler
    nh = get_node_handler()
    nh.add_node(from_node)
    nh.add_node(to_node)
    caller = Object.create(None, "DoorUser")
    caller.location = from_node
    # instrument Node.msg_contents to check door lock not held
    orig_msg = Node.msg_contents
    captured_locked = []

    def spy_msg(self, *a, **kw):
        # check if door.lock is held
        # RLock acquire non-blocking returns False if already held by current thread? But we are on same thread.
        # We check by trying to acquire in a separate thread or by checking _is_owned?
        # Use RLock internal: _is_owned
        try:
            is_locked = door.lock._is_owned()  # type: ignore[attr-defined]
        except Exception:
            # fallback: try acquire without blocking from another thread
            is_locked = False
            holder = []
            def try_acquire():
                acquired = door.lock.acquire(blocking=False)
                holder.append(acquired)
                if acquired:
                    door.lock.release()
            t = threading.Thread(target=try_acquire)
            t.start()
            t.join(timeout=1)
            if holder and not holder[0]:
                is_locked = True
        captured_locked.append(is_locked)
        return orig_msg(self, *a, **kw)

    with patch.object(Node, "msg_contents", spy_msg):
        # also patch map handler to avoid map side effects
        with patch("atheriz.objects.base_door.get_map_handler") as mock_mh:
            mock_mi = MagicMock()
            mock_mi.lock = threading.RLock()
            mock_mi.post_grid = {}
            mock_mi.pre_grid = {}
            mock_mi.map_changed = False
            mock_mi.render = MagicMock()
            mock_mh.return_value.get_mapinfo.return_value = mock_mi
            result = door.try_open(caller)
            assert result is True
    # at least one broadcast happened and none held lock
    assert len(captured_locked) >= 1
    assert not any(captured_locked), f"door lock held during broadcast: {captured_locked}"

    # also test try_close does not hold lock
    captured_locked.clear()
    door.closed = False
    # need caller location still from_node
    with patch.object(Node, "msg_contents", spy_msg):
        with patch("atheriz.objects.base_door.get_map_handler") as mock_mh:
            mock_mi = MagicMock()
            mock_mi.lock = threading.RLock()
            mock_mi.post_grid = {}
            mock_mi.pre_grid = {}
            mock_mi.map_changed = False
            mock_mi.render = MagicMock()
            mock_mh.return_value.get_mapinfo.return_value = mock_mi
            result = door.try_close(caller)
            assert result is True
    assert not any(captured_locked)


def test_session_prompt_binds_future_to_existing_loop(global_test_env):
    loop = asyncio.new_event_loop()
    conn = MagicMock()
    conn.loop = loop
    conn.send_command = MagicMock()
    conn.msg = MagicMock()
    sess = Session(connection=conn)

    async def run_prompt():
        with patch("atheriz.objects.session.asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            coro = sess.prompt("hello")
            with patch("atheriz.globals.get.get_async_threadpool") as mock_gtp:
                mock_pool = MagicMock()
                mock_pool.loop = loop
                mock_gtp.return_value = mock_pool
                task = loop.create_task(coro)
                await asyncio.sleep(0.05)
                fut = sess.input_future
                assert fut is not None
                try:
                    fut_loop = fut.get_loop()
                except RuntimeError:
                    fut_loop = None
                assert fut_loop is loop, f"future bound to {fut_loop} not {loop}"
                if not fut.done():
                    fut.set_result("answer")
                try:
                    result = await asyncio.wait_for(task, timeout=1)
                    assert result == "answer"
                except asyncio.TimeoutError:
                    task.cancel()
                    raise

    try:
        loop.run_until_complete(run_prompt())
    finally:
        loop.close()


def test_delay_does_not_resurrect_pool_after_shutdown(global_test_env):
    import atheriz.globals.get as get_mod
    from atheriz.globals.get import get_async_threadpool

    pool = get_async_threadpool()
    calls = []
    orig_add = pool.add_task
    pool.add_task = lambda func, *a, **kw: calls.append((func, a, kw)) or True

    captured = {}

    def fake_submit(coro, target_loop):
        captured["coro"] = coro
        captured["loop"] = target_loop
        return MagicMock()

    with patch("atheriz.globals.asyncthreadpool._submit", side_effect=fake_submit):
        pool.delay(0.1, lambda: None)

    assert "coro" in captured
    coro = captured["coro"]

    pool._stopped = True
    with get_mod._SINGLETON_LOCK:
        saved = get_mod._ASYNC_THREAD_POOL
        get_mod._ASYNC_THREAD_POOL = None

    async def instant_sleep(delay):
        return

    async def run_coro():
        with patch("atheriz.globals.asyncthreadpool.asyncio.sleep", instant_sleep):
            await coro

    tmp_loop = asyncio.new_event_loop()
    try:
        tmp_loop.run_until_complete(run_coro())
    finally:
        tmp_loop.close()

    assert len(calls) == 0, f"add_task called after shutdown: {calls}"
    assert get_mod._ASYNC_THREAD_POOL is None, "delay resurrected pool after shutdown"

    pool.add_task = orig_add
    pool._stopped = False
    with get_mod._SINGLETON_LOCK:
        if get_mod._ASYNC_THREAD_POOL is None:
            get_mod._ASYNC_THREAD_POOL = saved
