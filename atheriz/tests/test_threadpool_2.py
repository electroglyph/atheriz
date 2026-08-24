"""Issue #32: bounded threadpool task queue.

Verifies the intent of the flood-protection code:
- the queue has a finite, configured maxsize
- add_task rejects the newest task fast instead of blocking the caller
- accepted tasks still run; rejected tasks never run
- stop() completes when the queue is full, discarding pending work to make
  room for worker sentinels (shutdown must not hang)
"""
from __future__ import annotations

import queue
import threading
import time

import pytest

import atheriz.settings as settings
from atheriz.globals.asyncthreadpool import AsyncThreadPool


def _occupy_workers(atp, block):
    """Block every sync worker on `block` and return once all are busy.

    Workers read self.task_queue once per loop iteration, so the queue can
    only be safely swapped for a small test queue while all workers are
    busy executing (not parked in queue.get()).
    """
    n_workers = atp.max_threads - 1
    started = threading.Semaphore(0)

    def blocker():
        started.release()
        block.wait(5)

    for _ in range(n_workers):
        atp.add_task(blocker)
    for _ in range(n_workers):
        assert started.acquire(timeout=2), "worker did not pick up blocker"
    return n_workers


class TestAsyncThreadPool:
    def test_task_queue_is_bounded(self, global_test_env):
        """INTENT: the task queue has a finite maxsize of at least 10,000 so
        a flood of commands cannot grow it unboundedly."""
        atp = AsyncThreadPool()
        try:
            assert atp.task_queue.maxsize == settings.THREADPOOL_QUEUE_LIMIT
            assert atp.task_queue.maxsize >= 10_000
        finally:
            atp.stop(True, 10)

    def test_add_task_rejects_fast_when_full(self, global_test_env, monkeypatch):
        """INTENT: when the queue is full, add_task returns False quickly
        rather than blocking the producing thread. Elasticity is disabled so
        the zero-relief backpressure contract is isolated."""
        monkeypatch.setattr(settings, "THREADPOOL_RELIEF_LIMIT", 0)
        atp = AsyncThreadPool()
        block = threading.Event()
        try:
            _occupy_workers(atp, block)
            atp.task_queue = queue.Queue(maxsize=2)
            assert atp.add_task(lambda: None) is True
            assert atp.add_task(lambda: None) is True
            t0 = time.monotonic()
            assert atp.add_task(lambda: None) is False
            assert time.monotonic() - t0 < 0.5
        finally:
            block.set()
            atp.stop(False, 5)

    def test_accepted_tasks_run_rejected_do_not(self, global_test_env, monkeypatch):
        """INTENT: already accepted tasks still execute (FIFO); only the
        rejected newest tasks never run. Elasticity is disabled so the queue
        fills deterministically."""
        monkeypatch.setattr(settings, "THREADPOOL_RELIEF_LIMIT", 0)
        atp = AsyncThreadPool()
        block = threading.Event()
        ran = []
        try:
            _occupy_workers(atp, block)
            atp.task_queue = queue.Queue(maxsize=3)
            for i in range(3):
                assert atp.add_task(ran.append, i) is True
            assert atp.add_task(ran.append, 99) is False
            block.set()
            deadline = time.time() + 3
            while time.time() < deadline and len(ran) < 3:
                time.sleep(0.01)
            assert sorted(ran) == [0, 1, 2]
        finally:
            block.set()
            atp.stop(False, 5)

    def test_stop_completes_and_delivers_sentinels_when_full(self, global_test_env):
        """INTENT: stop() on a flooded queue does not hang; it discards
        pending work so every worker still receives a sentinel and exits."""
        atp = AsyncThreadPool()
        block = threading.Event()
        try:
            n_workers = _occupy_workers(atp, block)
            # capacity exactly fits the sentinels (max_threads) once every
            # junk task is discarded
            atp.task_queue = queue.Queue(maxsize=atp.max_threads)
            for _ in range(atp.max_threads):
                atp.task_queue.put_nowait((lambda: None, (), {}))
            t0 = time.monotonic()
            atp.stop(False, 5)
            assert time.monotonic() - t0 < 5, "stop() hung on a full queue"
            # the queue was full of junk; it now holds only sentinels
            assert atp.task_queue.qsize() == atp.max_threads
            # prove every worker got a sentinel: they all exit after unblock
            block.set()
            for t in atp.threads[1:]:
                t.join(timeout=3)
                assert not t.is_alive(), f"worker {t.name} never received a sentinel"
            # max_threads sentinels went in, max_threads-1 workers took one
            # each; the leftover must be a sentinel, i.e. every junk task
            # was discarded
            leftover = []
            while True:
                try:
                    leftover.append(atp.task_queue.get_nowait())
                except queue.Empty:
                    break
            assert leftover == [None]
        finally:
            block.set()
