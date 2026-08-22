"""Issue tests: changing AUTOSAVE_MINUTES between start/stop stacked duplicate
autosave ticks.

stop_autosave() recomputed the slot key from the CURRENT setting instead of
remembering what it registered. After a hot reload that changed the setting,
remove_coro targeted a nonexistent slot, the old tick kept firing forever, and
start_autosave added a second one — duplicates accumulating every reload cycle.
Fix: remember the registered interval at start time and remove exactly that key.
"""

from __future__ import annotations

import pytest

import atheriz.settings as settings
from atheriz.globals.autosave import autosave_tick, start_autosave, stop_autosave
from atheriz.globals.get import get_async_ticker


@pytest.fixture(autouse=True)
def _clean_autosave_state():
    from atheriz.globals import autosave

    stop_autosave()
    autosave._autosave_started = False
    autosave._registered_interval = None
    ticker = get_async_ticker()
    for interval in [float(m) * 60.0 for m in (1, 2, 5, 10)]:
        ticker.remove_coro(autosave_tick, interval)
    yield
    stop_autosave()
    autosave._autosave_started = False
    autosave._registered_interval = None
    for interval in [float(m) * 60.0 for m in (1, 2, 5, 10)]:
        ticker.remove_coro(autosave_tick, interval)


def _slots_holding_tick() -> list[float]:
    return [
        interval
        for interval, slot in get_async_ticker().slots.items()
        if autosave_tick in slot.coros
    ]


class TestStaleKeyRegression:
    def test_stop_removes_old_interval_after_setting_change(self, monkeypatch):
        """INTENT: register at 5 minutes, change the setting to 10, then stop:
        the tick must be gone from the OLD slot and start must not stack."""
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        start_autosave()
        assert _slots_holding_tick() == [300.0]

        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 10)
        stop_autosave()
        assert _slots_holding_tick() == []

        start_autosave()
        holding = _slots_holding_tick()
        assert holding == [600.0]
        assert len(holding) == 1

    def test_repeated_reload_cycles_never_stack(self, monkeypatch):
        """INTENT: cycling start/stop across changing intervals leaves exactly
        one registration at the latest interval — no residue in old slots."""
        for minutes in (1, 5, 2, 10):
            monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", minutes)
            stop_autosave()
            start_autosave()
            expected = float(minutes) * 60.0
            assert _slots_holding_tick() == [expected]


class TestDisabledTransition:
    def test_disable_with_changed_setting_still_removes(self, monkeypatch):
        """INTENT: disabling autosave (setting -> falsy) after the interval
        changed still removes the stored-interval registration; restart is a
        no-op."""
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        start_autosave()
        assert _slots_holding_tick() == [300.0]

        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 0)
        stop_autosave()
        assert _slots_holding_tick() == []

        start_autosave()
        assert _slots_holding_tick() == []
