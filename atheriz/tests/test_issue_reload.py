"""Issue tests: hot-reload (do_reload) clears the ticker but never restarts the
game clock or autosave, because the `started`/`_autosave_started` flags were
not reset.
"""
from __future__ import annotations

import pytest

from atheriz.globals.autosave import autosave_tick, start_autosave
from atheriz.globals.get import get_async_ticker, get_game_time
from atheriz.globals.startstop import do_reload
from atheriz import settings


class TestReloadKeepsGameClock:
    def test_reload_re_registers_game_clock(self, global_test_env):
        """INTENT: after a hot-reload the game clock coroutine must still be
        registered on the ticker. `do_reload` clears all ticker slots and then
        calls `start()` which is a no-op because the `started` flag survives."""
        gt = get_game_time()
        gt.start()
        ticker = get_async_ticker()
        slot = ticker.slots.get(settings.TIME_UPDATE_SECONDS)
        assert slot is not None
        assert gt.on_tick in slot.coros

        do_reload()

        ticker = get_async_ticker()
        slot = ticker.slots.get(settings.TIME_UPDATE_SECONDS)
        assert slot is not None
        assert gt.on_tick in slot.coros


class TestReloadKeepsAutosave:
    def test_reload_re_registers_autosave(self, global_test_env):
        """INTENT: after a hot-reload the autosave coroutine must still be
        registered on the ticker."""
        from atheriz.globals import autosave

        start_autosave()
        interval = float(settings.AUTOSAVE_MINUTES) * 60.0
        ticker = get_async_ticker()
        slot = ticker.slots.get(interval)
        assert slot is not None
        assert autosave_tick in slot.coros

        do_reload()

        ticker = get_async_ticker()
        slot = ticker.slots.get(interval)
        assert slot is not None
        assert autosave_tick in slot.coros
