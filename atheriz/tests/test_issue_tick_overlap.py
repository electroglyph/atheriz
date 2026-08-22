"""Issue tests: ticker dispatch had no overlap guard — `timer()` snapshotted
`self.coros` every interval and enqueued each one regardless of whether the
previous tick of the same coro had finished. A slow sync `at_tick` (they run
on threadpool workers) got queued again and two copies ran concurrently on
different workers, racing on object state.

Also: a worker thread died permanently if dispatch itself raised (e.g.
`run_coroutine_threadsafe` on a closed loop), and `add_task` kept accepting
tasks into a stopped pool where no worker would ever run them.

INTENT: a tick of a coro is skipped while the previous tick is still pending;
workers survive dispatch errors; a stopped pool rejects new tasks.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

from atheriz.globals.asyncthreadpool import AsyncThreadPool, AsyncTicker


class TestNoOverlappingTicks:
    def test_slow_tick_never_runs_concurrently(self, global_test_env):
        """INTENT: with interval 0.05 and a handler that takes 0.15s, ticks of
        the same coro must never overlap; missed intervals are skipped."""
        ticker = AsyncTicker()
        interval = 0.05
        lock = threading.Lock()
        state = {"active": 0, "overlap": 0, "runs": 0}

        def slow_tick():
            with lock:
                state["active"] += 1
                if state["active"] > 1:
                    state["overlap"] += 1
            time.sleep(0.15)
            with lock:
                state["active"] -= 1
                state["runs"] += 1

        try:
            ticker.add_coro(slow_tick, interval)
            time.sleep(0.8)
            ticker.remove_coro(slow_tick, interval)
        finally:
            ticker.stop()
            ticker.clear()

        assert state["overlap"] == 0, "at_tick ran concurrently with itself"
        assert state["runs"] >= 2, "slow tick never ran serially"

    def test_pending_blocks_only_the_busy_coro(self, global_test_env):
        """INTENT: one slow coro must not delay ticks of an unrelated coro in
        the same slot."""
        ticker = AsyncTicker()
        interval = 0.05
        fast_calls = []

        def slow_tick():
            time.sleep(0.2)

        def fast_tick():
            fast_calls.append(1)

        try:
            ticker.add_coro(slow_tick, interval)
            ticker.add_coro(fast_tick, interval)
            time.sleep(0.5)
            ticker.remove_coro(slow_tick, interval)
            ticker.remove_coro(fast_tick, interval)
        finally:
            ticker.stop()
            ticker.clear()

        assert len(fast_calls) >= 4, (
            f"fast coro dragged down by slow one ({len(fast_calls)} ticks in 0.5s)"
        )


class TestWorkerResilience:
    def test_worker_survives_dispatch_error(self, global_test_env):
        """INTENT: a task whose dispatch raises (coroutine handed to a dead
        loop) must be logged and the worker must keep processing; the old code
        let the worker thread die."""
        atp = AsyncThreadPool()
        ran = threading.Event()

        async def coro_task():
            pass

        try:
            with patch(
                "atheriz.globals.asyncthreadpool.asyncio.run_coroutine_threadsafe",
                side_effect=RuntimeError("event loop is closed"),
            ):
                assert atp.add_task(coro_task) is True
                assert atp.add_task(ran.set) is True
                assert ran.wait(5), "worker died instead of surviving dispatch error"
        finally:
            atp.stop(False, 5)

    def test_add_task_rejected_after_stop(self, global_test_env):
        """INTENT: a stopped pool must refuse new tasks (add_task -> False);
        the old code accepted them into a queue nobody drained."""
        atp = AsyncThreadPool()
        try:
            atp.stop(False, 5)
            assert atp.add_task(lambda: None) is False
        finally:
            pass


class TestNoLeakedCoroutines:
    def test_failed_dispatch_closes_coroutine(self, global_test_env):
        """INTENT: when dispatch raises (coroutine handed to a dead loop), the
        wrapped coroutine must be closed, not leaked — a leaked coroutine makes
        GC emit 'coroutine ... was never awaited' at an arbitrary later point
        (previously surfacing as a warning during unrelated tests)."""
        import gc
        import warnings

        atp = AsyncThreadPool()

        async def coro_task():
            pass

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with patch(
                    "atheriz.globals.asyncthreadpool.asyncio.run_coroutine_threadsafe",
                    side_effect=RuntimeError("event loop is closed"),
                ):
                    assert atp.add_task(coro_task) is True
                    done = threading.Event()
                    assert atp.add_task(done.set) is True
                    assert done.wait(5), "worker died instead of surviving dispatch error"
                gc.collect()
            leaked = [w for w in caught if "never awaited" in str(w.message)]
            assert leaked == [], f"leaked coroutine(s): {[str(w.message) for w in leaked]}"
        finally:
            atp.stop(False, 5)

    def test_delay_failure_closes_coroutine_and_propagates(self, global_test_env):
        """INTENT: delay() must also close its wrapper coroutine when the
        submit fails; the original error still propagates to the caller."""
        import gc
        import warnings

        import pytest

        atp = AsyncThreadPool()

        async def task():
            pass

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with patch(
                    "atheriz.globals.asyncthreadpool.asyncio.run_coroutine_threadsafe",
                    side_effect=RuntimeError("event loop is closed"),
                ):
                    with pytest.raises(RuntimeError):
                        atp.delay(0.1, task)
                gc.collect()
            leaked = [w for w in caught if "never awaited" in str(w.message)]
            assert leaked == [], f"leaked coroutine(s): {[str(w.message) for w in leaked]}"
        finally:
            atp.stop(False, 5)
