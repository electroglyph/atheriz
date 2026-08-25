"""Issue tests: threadpool starvation had no elasticity and no diagnostics.

AsyncThreadPool ran sync tasks inline on a fixed set of workers; any task
blocking on another queued task could consume all workers and permanently
starve the pool, silently. Fix (Layer 1 + Layer 2): elastic relief workers
spawned when the queue holds work while every fixed worker is busy (capped,
cooldown-gated, retiring when the queue drains), plus a watchdog that logs a
throttled starvation warning with per-worker diagnostics.
"""

from __future__ import annotations

import threading
import time

import pytest

from atheriz.globals.asyncthreadpool import AsyncThreadPool


@pytest.fixture
def tiny_pool():
    pool = AsyncThreadPool(max_threads=2)
    baseline = threading.active_count()
    yield pool, baseline
    pool.stop(wait=True)


def _wait(cond, timeout=5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


class TestReliefWorkers:
    def test_backlog_drains_when_fixed_workers_blocked(self, tiny_pool):
        """INTENT: with the single sync worker blocked on a long task, queued
        tasks must still complete via spawned relief workers."""
        pool, _baseline = tiny_pool
        release = threading.Event()
        done = []
        started = threading.Event()

        def blocker():
            started.set()
            release.wait(10)

        def quick(i):
            done.append(i)

        pool.add_task(blocker)
        assert started.wait(2)
        for i in range(10):
            pool.add_task(quick, i)

        assert _wait(lambda: len(done) == 10), f"only {len(done)}/10 tasks ran"
        release.set()
        assert _wait(lambda: pool._busy == 0)

    def test_relief_workers_retire_after_queue_drains(self, tiny_pool):
        """INTENT: temporary relief threads exit once the queue is empty —
        thread count returns to (at or below) its pre-burst level."""
        pool, _baseline = tiny_pool
        release = threading.Event()
        started = threading.Event()

        pool.add_task(lambda: (started.set(), release.wait(10)))
        assert started.wait(2)
        for i in range(5):
            pool.add_task(time.sleep, 0)
        release.set()

        assert _wait(lambda: not pool._relief_threads or all(not t.is_alive() for t in pool._relief_threads))
        assert pool._relief_count == 0

    def test_no_relief_when_pool_healthy(self, tiny_pool):
        """INTENT: fast tasks below capacity never trigger a spawn — no extra
        threads appear while the worker keeps up."""
        pool, baseline = tiny_pool
        for i in range(50):
            pool.add_task(lambda: None)

        assert _wait(lambda: pool.task_queue.qsize() == 0)
        assert pool._relief_count == 0
        assert pool._relief_threads == []

    def test_spawn_respects_cooldown_and_cap(self, tiny_pool, monkeypatch):
        """INTENT: spawns are cooldown-gated and hard-capped so a burst cannot
        grow the pool without bound."""
        import atheriz.settings as settings

        monkeypatch.setattr(settings, "THREADPOOL_RELIEF_LIMIT", 2)
        pool, _ = tiny_pool
        release = threading.Event()
        started = threading.Event()
        pool.add_task(lambda: (started.set(), release.wait(10)))
        assert started.wait(2)

        # spam enqueues; cap must hold even though every enqueue sees saturation
        for i in range(20):
            pool.add_task(time.sleep, 0)
            time.sleep(0.01)

        assert pool._relief_count <= 2
        release.set()


class TestWatchdog:
    def test_starvation_logged_once_when_saturated(self, monkeypatch, capture_atheriz_log):
        """INTENT: sustained full saturation past the threshold emits exactly
        one starvation error within the window; throttle prevents repeats."""
        import atheriz.settings as settings

        monkeypatch.setattr(settings, "THREADPOOL_WATCHDOG_SECONDS", 0.5)
        monkeypatch.setattr(settings, "THREADPOOL_WATCHDOG_INTERVAL", 0.1)
        monkeypatch.setattr(settings, "THREADPOOL_RELIEF_LIMIT", 0)
        pool = AsyncThreadPool(max_threads=2)
        try:
            read = capture_atheriz_log
            gate = threading.Event()
            started = threading.Event()

            def blocker():
                started.set()
                gate.wait(10)

            pool.add_task(blocker)
            assert started.wait(2)
            for i in range(3):
                pool.add_task(time.sleep, 0.05)

            def starve_logs():
                return read().count("starvation suspected")

            assert _wait(lambda: starve_logs() >= 1, timeout=5.0)
            time.sleep(0.15)
            assert starve_logs() == 1
            # diagnostics must name the running task, not a thread ident
            assert "blocker running" in read()
            gate.set()
        finally:
            pool.stop(wait=True)


class TestSentinelShortage:
    def test_relief_worker_requeues_sentinel_when_stopped(self):
        """INTENT: a relief worker that pulls a sentinel on a stopped pool
        must re-queue it and retire, never consuming a fixed worker's kill
        signal."""
        pool = AsyncThreadPool(max_threads=2)
        pool.stop(wait=True, timeout=5)
        # fixed worker consumed its sentinel and died; no spare remains (max_threads-1 sentinels)
        spare = pool.task_queue.qsize()
        assert spare == 0
        pool._relief_count = 1
        t = threading.Thread(
            target=pool._work_loop, kwargs={"relief": True}, daemon=True
        )
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "relief worker did not retire on stopped pool"
        assert pool.task_queue.qsize() == spare, (
            "relief worker consumed a sentinel meant for a fixed worker"
        )
        assert pool._relief_count == 0

    def test_stop_with_competing_relief_workers_stops_all_fixed_workers(
        self, monkeypatch
    ):
        """INTENT: relief workers mid-drain at stop() time retire on
        re-queued sentinels, so every fixed worker still receives a kill
        signal and stop(wait=True) returns with no worker left alive."""
        import atheriz.settings as settings

        monkeypatch.setattr(settings, "THREADPOOL_RELIEF_LIMIT", 8)
        monkeypatch.setattr(AsyncThreadPool, "RELIEF_SPAWN_COOLDOWN", 0)
        pool = AsyncThreadPool(max_threads=2)
        gate = threading.Event()
        occupied = [threading.Event() for _ in range(4)]

        def blocker(ev):
            ev.set()
            gate.wait(10)

        try:
            # sequential adds: each occupied slot guarantees _busy was
            # incremented, so the next add reliably spawns a relief worker
            for ev in occupied:
                assert pool.add_task(blocker, ev)
                assert ev.wait(5), "worker did not pick up blocker"
            assert pool._relief_count >= 2, "test requires multiple relief workers"

            stopper = threading.Thread(
                target=pool.stop,
                kwargs={"wait": True, "timeout": 10},
                daemon=True,
            )
            stopper.start()
            gate.set()
            stopper.join(timeout=30)
            assert not stopper.is_alive(), "stop() did not return"
            assert all(not t.is_alive() for t in pool.threads[1:]), (
                "fixed worker starved of its sentinel"
            )
            assert all(not t.is_alive() for t in pool._relief_threads), (
                "relief worker did not retire"
            )
        finally:
            gate.set()
            if not pool._stopped:
                pool.stop(wait=False, timeout=5)
