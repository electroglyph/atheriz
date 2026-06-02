"""Tests for atheriz.globals.get — singleton getters and ID counter."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

import atheriz.globals.get as get_singleton
from atheriz.globals.get import (
    get_async_threadpool,
    get_async_ticker,
    get_connection_manager,
    get_game_time,
    get_loggedin_cmdset,
    get_map_handler,
    get_node_handler,
    get_server_channel,
    get_unique_id,
    get_unloggedin_cmdset,
    set_id,
)


@pytest.fixture(autouse=True)
def reset_all_singletons(global_test_env):
    """Reset all module-level singletons so each test gets a fresh state."""
    get_singleton._GAME_TIME = None
    get_singleton._SERVER_CHANNEL = None
    get_singleton._ASYNC_THREAD_POOL = None
    get_singleton._ASYNC_TICKER = None
    get_singleton._MAP_HANDLER = None
    get_singleton._NODE_HANDLER = None
    get_singleton._LOGGEDIN_CMDSET = None
    get_singleton._UNLOGGEDIN_CMDSET = None
    get_singleton._CONNECTION_MANAGER = None
    yield


class TestUniqueId:
    def test_set_id_changes_counter(self, global_test_env):
        set_id(0)
        assert get_unique_id() == 1

    def test_id_increments(self, global_test_env):
        set_id(0)
        id1 = get_unique_id()
        id2 = get_unique_id()
        assert id2 == id1 + 1

    def test_id_strictly_monotonic(self, global_test_env):
        set_id(0)
        ids = [get_unique_id() for _ in range(10)]
        for a, b in zip(ids, ids[1:]):
            assert b == a + 1

    def test_set_id_overrides(self, global_test_env):
        set_id(100)
        assert get_unique_id() == 101
        assert get_unique_id() == 102

    def test_set_id_to_zero(self, global_test_env):
        set_id(0)
        assert get_unique_id() == 1

    def test_set_id_negative(self, global_test_env):
        set_id(-5)
        assert get_unique_id() == -4

    def test_id_unique_across_threads(self, global_test_env):
        # INTENT: lock guarantees no duplicate IDs even under concurrency
        set_id(0)
        seen = []
        lock = threading.Lock()

        def worker():
            for _ in range(50):
                nid = get_unique_id()
                with lock:
                    seen.append(nid)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All IDs must be unique
        assert len(seen) == len(set(seen))
        # Expected count
        assert len(seen) == 4 * 50
        # And they form a contiguous range
        assert max(seen) - min(seen) == len(seen) - 1

    def test_id_starts_from_minus_one_after_reset(self, global_test_env):
        # After global_test_env resets _ID to -1
        first = get_unique_id()
        assert first == 0  # -1 + 1 = 0


class TestGetGameTime:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.globals.time.GameTime") as MockCls:
            MockCls.return_value = MagicMock(name="game_time")
            t1 = get_game_time()
            t2 = get_game_time()
        assert t1 is t2
        # GameTime was only constructed once
        assert MockCls.call_count == 1


class TestGetConnectionManager:
    def test_returns_singleton(self, global_test_env):
        m1 = get_connection_manager()
        m2 = get_connection_manager()
        assert m1 is m2

    def test_returns_module(self, global_test_env):
        # ConnectionManager is just the module (no instance)
        from atheriz.network import connection_manager
        assert get_connection_manager() is connection_manager


class TestGetAsyncTicker:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.globals.asyncthreadpool.AsyncTicker") as MockCls:
            MockCls.return_value = MagicMock()
            t1 = get_async_ticker()
            t2 = get_async_ticker()
        assert t1 is t2
        assert MockCls.call_count == 1

    def test_constructed_once(self, global_test_env):
        with patch("atheriz.globals.asyncthreadpool.AsyncTicker") as MockCls:
            MockCls.return_value = MagicMock()
            get_async_ticker()
            get_async_ticker()
        assert MockCls.call_count == 1


class TestGetServerChannel:
    def test_returns_none_when_no_channel(self, global_test_env):
        with patch("atheriz.globals.objects.filter_by", return_value=[]):
            assert get_server_channel() is None

    def test_returns_first_matching_channel(self, global_test_env):
        chan = MagicMock()
        with patch("atheriz.globals.objects.filter_by", return_value=[chan]):
            result = get_server_channel()
        assert result is chan

    def test_caches_after_first_lookup(self, global_test_env):
        chan = MagicMock()
        with patch("atheriz.globals.objects.filter_by", return_value=[chan]) as mock_fb:
            get_server_channel()
            get_server_channel()
        # filter_by should only be called once (after which _SERVER_CHANNEL is cached)
        assert mock_fb.call_count == 1

    def test_returns_cached_on_subsequent_calls(self, global_test_env):
        chan = MagicMock()
        with patch("atheriz.globals.objects.filter_by", return_value=[chan]):
            first = get_server_channel()
        # Second call without filter_by in scope — but cached
        # Need to reset mock to verify no new call
        with patch("atheriz.globals.objects.filter_by") as mock_fb:
            second = get_server_channel()
        assert first is second
        mock_fb.assert_not_called()


class TestGetMapHandler:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.globals.map.MapHandler") as MockCls:
            MockCls.return_value = MagicMock()
            m1 = get_map_handler()
            m2 = get_map_handler()
        assert m1 is m2
        assert MockCls.call_count == 1


class TestGetLoggedinCmdset:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.commands.loggedin.cmdset.LoggedinCmdSet") as MockCls:
            MockCls.return_value = MagicMock()
            c1 = get_loggedin_cmdset()
            c2 = get_loggedin_cmdset()
        assert c1 is c2
        assert MockCls.call_count == 1


class TestGetUnloggedinCmdset:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.commands.unloggedin.cmdset.UnloggedinCmdSet") as MockCls:
            MockCls.return_value = MagicMock()
            c1 = get_unloggedin_cmdset()
            c2 = get_unloggedin_cmdset()
        assert c1 is c2
        assert MockCls.call_count == 1


class TestGetAsyncThreadpool:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.globals.asyncthreadpool.AsyncThreadPool") as MockCls:
            MockCls.return_value = MagicMock()
            t1 = get_async_threadpool()
            t2 = get_async_threadpool()
        assert t1 is t2
        assert MockCls.call_count == 1

    def test_constructed_with_threadpool_limit(self, global_test_env):
        with patch("atheriz.globals.asyncthreadpool.AsyncThreadPool") as MockCls:
            MockCls.return_value = MagicMock()
            from atheriz.settings import THREADPOOL_LIMIT
            get_async_threadpool()
        # The limit is passed as a positional arg
        assert MockCls.call_args.args[0] == THREADPOOL_LIMIT


class TestGetNodeHandler:
    def test_returns_singleton(self, global_test_env):
        with patch("atheriz.globals.node.NodeHandler") as MockCls:
            MockCls.return_value = MagicMock()
            n1 = get_node_handler()
            n2 = get_node_handler()
        assert n1 is n2
        assert MockCls.call_count == 1


class TestIntegration:
    def test_getters_are_independent(self, global_test_env):
        # Each getter manages its own singleton — creating one doesn't create another
        with patch("atheriz.globals.time.GameTime") as gt_cls, \
             patch("atheriz.globals.map.MapHandler") as mh_cls, \
             patch("atheriz.globals.node.NodeHandler") as nh_cls:
            gt_cls.return_value = MagicMock()
            mh_cls.return_value = MagicMock()
            nh_cls.return_value = MagicMock()
            gt = get_game_time()
            mh = get_map_handler()
            nh = get_node_handler()
        assert gt is not mh
        assert mh is not nh
        assert gt is not nh
