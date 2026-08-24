"""Issue tests: GameTime.stop() never resets `started`, so a later start() is a
no-op; and non-repeat wildcard alarms are never removed because removal looks
up the exact (hour, minute) key instead of the wildcard key.
"""
from __future__ import annotations

import pytest

from atheriz import settings
from atheriz.globals.get import get_async_ticker, get_game_time
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object


class TestGameTimeRestart:
    def test_restart_after_stop_re_registers_clock(self, global_test_env):
        """INTENT: after stop() the game clock must be startable again.
        stop() never resets the `started` flag, so start() is a no-op and the
        on_tick coroutine is never re-registered."""
        gt = get_game_time()
        gt.start()

        ticker = get_async_ticker()
        slot = ticker.slots.get(settings.TIME_UPDATE_SECONDS)
        assert slot is not None
        assert gt.on_tick in slot.coros

        gt.stop()
        gt.start()

        ticker = get_async_ticker()
        slot = ticker.slots.get(settings.TIME_UPDATE_SECONDS)
        assert slot is not None
        assert gt.on_tick in slot.coros


class TestWildcardAlarms:
    def test_non_repeat_wildcard_alarm_is_removed(self, global_test_env):
        """INTENT: a non-repeat alarm registered on a wildcard hour ('?') must
        be removed after it fires once. The removal currently looks up the
        exact (hour, minute) key, so the wildcard entry survives and re-fires
        every matching hour."""
        gt = get_game_time()
        obj = Object.create(None, "alarmee")
        add_object(obj)

        gt.ticks = 1
        minute = str(gt.get_time()["minute"])  # the minute the clock will read after the tick
        gt.ticks = 0
        gt.add_alarm("?", minute, obj, repeat=False)

        gt.on_tick()

        assert gt.alarms.get(("?", minute)) == []  # entry removed; won't re-fire
