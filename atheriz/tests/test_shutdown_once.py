"""Issue tests: #5 — `do_shutdown()` runs twice on a graceful stop.

`/_internal/shutdown` calls `do_shutdown()` directly (atheriz.py:233), then the
`finally:` block in `run_server` calls it a second time (atheriz.py:394-399).
A second invocation must be a no-op: finalization hooks/broadcasts/saves must
run exactly once across the whole stop.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import atheriz.globals.startstop as ss


class TestDoShutdownIsIdempotent:
    def test_second_shutdown_call_is_a_noop(self, global_test_env):
        """INTENT: two `do_shutdown()` invocations must run the shutdown sequence
        exactly once (the `/_internal/shutdown` call plus the `finally:` block).
        Today both calls re-run at_server_stop, save_objects, msg_all and
        threadpool.stop -> every counter is 2."""
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects") as m_save, \
             patch.object(ss, "stop_autosave") as m_stop_auto, \
             patch("atheriz.server_events", create=True) as m_se, \
             patch.object(ss, "get_map_handler", return_value=MagicMock()) as m_mh, \
             patch.object(ss, "get_node_handler", return_value=MagicMock()) as m_nh, \
             patch.object(ss, "get_async_ticker", return_value=MagicMock()) as m_ticker, \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()) as m_tp, \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=MagicMock()) as m_db, \
             patch.object(ss, "msg_all") as m_msg_all, \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", True):
            ss.do_shutdown()
            # first run does a full shutdown
            m_se.at_server_stop.assert_called_once()

            # second run is the duplicated finalization from run_server
            ss.do_shutdown()

        # INTENT: neither the shutdown hook, the save, the broadcast, nor the
        # DB close may fire a second time.
        m_se.at_server_stop.assert_called_once()
        m_save.assert_called_once()
        m_msg_all.assert_called_once()
        m_db.return_value.close.assert_called_once()
        m_stop_auto.assert_called_once()
        m_ticker.return_value.stop.assert_called_once()
        m_tp.return_value.stop.assert_called_once()