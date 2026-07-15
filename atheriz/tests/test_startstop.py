"""Tests for atheriz.globals.startstop — server lifecycle (start/stop/reload)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import atheriz.globals.startstop as ss
from atheriz.tests.fakes import make_object

# Force-import server_events so it's available as a module attribute for patching
import atheriz.server_events  # noqa: F401


@pytest.fixture
def reset_singletons(global_test_env):
    """Force getters to return fresh mocks each call."""
    # The global_test_env fixture already resets these, but explicit reset here
    # ensures module-level module reloads don't pollute between tests.
    yield


def _channel():
    c = MagicMock()
    c.msg = MagicMock()
    return c


class TestDoStartup:
    def test_calls_load_objects(self, reset_singletons):
        with patch.object(ss, "load_objects") as mock_load, \
             patch.object(ss, "start_autosave") as mock_start, \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False):
            ss.do_startup()
        mock_load.assert_called_once()

    def test_initializes_threadpool_map_node_ticker(self, reset_singletons):
        with patch.object(ss, "load_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()) as m_tp, \
             patch.object(ss, "get_map_handler", return_value=MagicMock()) as m_mh, \
             patch.object(ss, "get_node_handler", return_value=MagicMock()) as m_nh, \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()) as m_at, \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False):
            ss.do_startup()
        m_tp.assert_called_once()
        m_mh.assert_called_once()
        m_nh.assert_called_once()
        m_at.assert_called_once()

    def test_calls_at_server_start(self, reset_singletons):
        with patch.object(ss, "load_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False):
            ss.do_startup()
        mock_se.at_server_start.assert_called_once()

    def test_starts_game_time_when_enabled(self, reset_singletons):
        with patch.object(ss, "load_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()) as mock_gt, \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", True):
            ss.do_startup()
        mock_gt.return_value.start.assert_called_once()

    def test_does_not_start_game_time_when_disabled(self, reset_singletons):
        with patch.object(ss, "load_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()) as mock_gt, \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False):
            ss.do_startup()
        mock_gt.assert_not_called()
        mock_gt.return_value.start.assert_not_called()

    def test_starts_autosave(self, reset_singletons):
        with patch.object(ss, "load_objects"), \
             patch.object(ss, "start_autosave") as mock_start_auto, \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False):
            ss.do_startup()
        mock_start_auto.assert_called_once()

    def test_full_startup_order(self, reset_singletons):
        # INTENT: load_objects happens before server_events hook
        order = []
        with patch.object(ss, "load_objects", side_effect=lambda: order.append("load")) as mock_load, \
             patch.object(ss, "start_autosave", side_effect=lambda: order.append("auto")), \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_async_threadpool", side_effect=lambda: order.append("tp") or MagicMock()), \
             patch.object(ss, "get_map_handler", side_effect=lambda: order.append("mh") or MagicMock()), \
             patch.object(ss, "get_node_handler", side_effect=lambda: order.append("nh") or MagicMock()), \
             patch.object(ss, "get_async_ticker", side_effect=lambda: order.append("at") or MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False):
            mock_se.at_server_start.side_effect = lambda: order.append("se_start")
            ss.do_startup()
        # autosave should come after server_events hook
        assert "load" in order
        assert "se_start" in order
        assert "auto" in order
        assert order.index("load") < order.index("se_start") < order.index("auto")


class TestDoShutdown:
    def test_broadcasts_to_channel_when_present(self, reset_singletons):
        chan = _channel()
        with patch.object(ss, "get_server_channel", return_value=chan), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        chan.msg.assert_called_once()
        assert "shutting down" in chan.msg.call_args.args[0].lower()

    def test_skips_broadcast_when_no_channel(self, reset_singletons):
        # INTENT: must not crash when channel is None
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()  # should not raise

    def test_calls_at_server_stop(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        mock_se.at_server_stop.assert_called_once()

    def test_saves_when_autosave_on_shutdown(self, reset_singletons):
        mh = MagicMock()
        nh = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects") as mock_save, \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=mh), \
             patch.object(ss, "get_node_handler", return_value=nh), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", True):
            ss.do_shutdown()
        mock_save.assert_called_once()
        mh.save.assert_called_once()
        nh.save.assert_called_once()

    def test_skips_saves_when_autosave_disabled(self, reset_singletons):
        mh = MagicMock()
        nh = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects") as mock_save, \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=mh), \
             patch.object(ss, "get_node_handler", return_value=nh), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        mock_save.assert_not_called()
        mh.save.assert_not_called()
        nh.save.assert_not_called()

    def test_stops_autosave_ticker_threadpool(self, reset_singletons):
        ticker = MagicMock()
        threadpool = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave") as mock_stop_auto, \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=ticker), \
             patch.object(ss, "get_async_threadpool", return_value=threadpool), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        mock_stop_auto.assert_called_once()
        ticker.stop.assert_called_once()
        threadpool.stop.assert_called_once()
        # INTENT: threadpool.stop waits for threads to drain with 10s timeout
        threadpool.stop.assert_called_with(True, 10)

    def test_msg_all_broadcasts_to_all(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all") as mock_msg_all, \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        mock_msg_all.assert_called_once()
        assert "shutting down" in mock_msg_all.call_args.args[0].lower()

    def test_stops_game_time_when_enabled(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()) as mock_gt, \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", True), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        mock_gt.return_value.stop.assert_called_once()

    def test_does_not_stop_game_time_when_disabled(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()) as mock_gt, \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        mock_gt.assert_not_called()

    def test_closes_database(self, reset_singletons):
        db = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=db), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            ss.do_shutdown()
        db.close.assert_called_once()


class TestDoReload:
    def test_broadcasts_reload_to_channel(self, reset_singletons):
        chan = _channel()
        with patch.object(ss, "get_server_channel", return_value=chan), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        # INTENT: msg sent twice — "reloading" at start, "reloaded" at end
        assert chan.msg.call_count == 2
        first = chan.msg.call_args_list[0].args[0]
        last = chan.msg.call_args_list[-1].args[0]
        assert "reloading" in first.lower()
        assert "reloaded" in last.lower()
        # The "reloading" message comes first
        assert "reloading" in first.lower()
        assert "reloaded" in last.lower()

    def test_skips_broadcast_when_no_channel(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()  # should not raise

    def test_runs_at_server_reload_hook(self, reset_singletons):
        # INTENT: do_reload invokes the at_server_reload hook
        # (Documents behavior: in normal mode where 'server_events' isn't a top-level
        # module, the except branch imports atheriz.server_events and calls its hook.
        # importlib.reload is only used in legacy 'server_events' module mode.)
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        mock_se.at_server_reload.assert_called_once()

    def test_calls_at_server_reload(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        mock_se.at_server_reload.assert_called_once()

    def test_clears_async_ticker(self, reset_singletons):
        ticker = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=ticker), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        ticker.clear.assert_called_once()

    def test_saves_when_autosave_on_reload(self, reset_singletons):
        mh = MagicMock()
        nh = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects") as mock_save, \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=mh), \
             patch.object(ss, "get_node_handler", return_value=nh), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", True):
            ss.do_reload()
        mock_save.assert_called_once()
        mh.save.assert_called_once()
        nh.save.assert_called_once()

    def test_skips_saves_when_autosave_disabled(self, reset_singletons):
        mh = MagicMock()
        nh = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects") as mock_save, \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=mh), \
             patch.object(ss, "get_node_handler", return_value=nh), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        mock_save.assert_not_called()
        mh.save.assert_not_called()
        nh.save.assert_not_called()

    def test_starts_autosave_after_reload(self, reset_singletons):
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave") as mock_start, \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        mock_start.assert_called_once()

    def test_reload_re_registers_time_ticker(self, reset_singletons):
        mock_gt = MagicMock()
        ticker = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "start_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_async_ticker", return_value=ticker), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=mock_gt), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", True), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
            ss.do_reload()
        ticker.clear.assert_called_once()
        mock_gt.start.assert_called_once()


class TestLifecycleOrder:
    def test_shutdown_runs_at_server_stop_before_db_close(self, reset_singletons):
        # INTENT: at_server_stop hook runs before the database is closed
        order = []
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events") as mock_se, \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()) as mock_db, \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
            mock_se.at_server_stop.side_effect = lambda: order.append("server_stop")
            mock_db.return_value.close.side_effect = lambda: order.append("db_close")
            ss.do_shutdown()
        assert "server_stop" in order
        assert "db_close" in order
        assert order.index("server_stop") < order.index("db_close")

    def test_shutdown_saves_before_stopping_threads(self, reset_singletons):
        # INTENT: all saves must happen after threadpool is stopped so no
        # async task can mutate objects between save and db.close
        order = []
        threadpool = MagicMock()
        threadpool.stop.side_effect = lambda *a, **kw: order.append("tp_stop")
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects", side_effect=lambda: order.append("save_obj")), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
             patch.object(ss, "get_async_threadpool", return_value=threadpool), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", True):
            ss.do_shutdown()
        assert "tp_stop" in order
        assert "save_obj" in order
        assert order.index("tp_stop") < order.index("save_obj")
