"""Issue tests: #23 — `AsyncTicker.add_coro` for an interval that is not yet
registered had a lost-update race (two threads each built a TimeSlot; the loser
was overwritten). Current code creates the slot under `self.lock`, so both
coroutines must end up in the SAME slot.

This is a green (already-fixed) regression guard, not a red defect pin.
"""
from __future__ import annotations

import threading

from atheriz.globals.asyncthreadpool import AsyncTicker


def test_concurrent_add_coro_same_interval_registers_both(global_test_env):
    ticker = AsyncTicker()
    interval = 0.05
    registered = set()

    def coro_a():
        registered.add("a")

    def coro_b():
        registered.add("b")

    barrier = threading.Barrier(2)

    def add_a():
        barrier.wait()
        ticker.add_coro(coro_a, interval)

    def add_b():
        barrier.wait()
        ticker.add_coro(coro_b, interval)

    t1 = threading.Thread(target=add_a)
    t2 = threading.Thread(target=add_b)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    try:
        slot = ticker.slots.get(interval)
        assert slot is not None, "no slot was created for the interval"
        # both coroutines must be tracked by the same slot
        assert coro_a in slot.coros, "coro_a was lost by the race"
        assert coro_b in slot.coros, "coro_b was lost by the race"
    finally:
        ticker.remove_coro(coro_a, interval)
        ticker.remove_coro(coro_b, interval)
        ticker.stop()
        ticker.clear()