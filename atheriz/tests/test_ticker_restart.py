"""Issue tests: `do_shutdown()` reset the global threadpool singleton but not
the global ticker, and every `AsyncTicker.TimeSlot` cached the pool it was
built with. After a shutdown/reboot inside one process, slots that already
existed (e.g. the game clock's 1s interval) re-armed their timer on the dead
pool's loop: `run_coroutine_threadsafe` enqueued a callback nobody ran, the
timer never ticked again, and nothing errored.

INTENT: shutdown drops BOTH singletons so a later boot gets a fresh ticker
bound to the fresh pool, and ticking demonstrably resumes after a reboot.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import atheriz.globals.get as get_singleton
import atheriz.globals.startstop as ss
import atheriz.settings as settings
from atheriz.globals.asyncthreadpool import AsyncTicker
from atheriz.globals.get import get_async_threadpool, get_async_ticker
from atheriz.globals.startstop import do_shutdown


def _shutdown_with_externals_mocked():
    with patch.object(ss, "get_server_channel", return_value=None), \
         patch.object(ss, "get_map_handler", return_value=MagicMock()), \
         patch.object(ss, "get_node_handler", return_value=MagicMock()), \
         patch.object(ss, "get_database", return_value=MagicMock()), \
         patch.object(ss, "msg_all"), \
         patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
         patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False), \
         patch("atheriz.server_events"):
        do_shutdown()


class TestShutdownResetsTickerAndPool:
    def test_do_shutdown_drops_both_singletons(self, global_test_env, monkeypatch):
        """INTENT: after do_shutdown both the pool and the ticker singletons
        are None; the old code left the ticker bound to the dead pool."""
        old_ticker = get_async_ticker()
        old_pool = get_async_threadpool()

        _shutdown_with_externals_mocked()

        assert get_singleton._ASYNC_THREAD_POOL is None
        assert get_singleton._ASYNC_TICKER is None
        assert get_async_ticker() is not old_ticker
        assert get_async_threadpool() is not old_pool

    def test_ticking_resumes_after_in_process_reboot(self, global_test_env):
        """INTENT: a coro registered at a pre-existing interval after a
        shutdown/reboot must actually tick. The old code re-armed the old
        slot's timer on the dead loop and it never fired."""
        calls = []

        def tick():
            calls.append(1)

        ticker = get_async_ticker()
        ticker.add_coro(tick, 0.05)
        time.sleep(0.2)
        assert len(calls) >= 2, "ticking never started before shutdown"

        _shutdown_with_externals_mocked()

        calls.clear()
        get_async_ticker().add_coro(tick, 0.05)
        time.sleep(0.25)
        assert len(calls) >= 2, (
            f"ticking dead after in-process reboot ({len(calls)} ticks in 0.25s)"
        )


class TestShutdownStepIsolation:
    def test_hook_failure_does_not_skip_remaining_steps(self, global_test_env):
        """INTENT: a raising at_server_stop hook must not skip autosave-on-
        shutdown, the ticker/pool stops, or the database close."""
        db = MagicMock()
        ticker = MagicMock()
        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects") as mock_save, \
             patch.object(ss, "get_async_ticker", return_value=ticker), \
             patch.object(ss, "get_async_threadpool", return_value=MagicMock()), \
             patch.object(ss, "get_map_handler", return_value=MagicMock()), \
             patch.object(ss, "get_node_handler", return_value=MagicMock()), \
             patch.object(ss, "get_game_time", return_value=MagicMock()), \
             patch.object(ss, "get_database", return_value=db), \
             patch.object(ss, "msg_all"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", True), \
             patch("atheriz.server_events") as mock_se:
            mock_se.at_server_stop.side_effect = RuntimeError("boom")
            ss.do_shutdown()
        mock_save.assert_called_once()
        ticker.stop.assert_called_once()
        db.close.assert_called_once()


class TestTickerStopIsolation:
    def test_stop_continues_past_raising_slot(self, global_test_env):
        """INTENT: one slot whose stop() raises must not prevent the remaining
        slots from being stopped (the old bare except aborted the loop)."""
        ticker = AsyncTicker()

        class BadSlot:
            interval = 0.01

            def stop(self):
                raise RuntimeError("boom")

        class GoodSlot:
            interval = 0.02

            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        ticker.slots[0.01] = BadSlot()
        good = GoodSlot()
        ticker.slots[0.02] = good

        ticker.stop()

        assert good.stopped, "stop() aborted before reaching the last slot"
