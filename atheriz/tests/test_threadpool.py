import pytest
import time
import threading
import asyncio
import functools
import queue
from typing import NoReturn
from unittest.mock import MagicMock, patch
from atheriz.globals.asyncthreadpool import AsyncThreadPool, AsyncTicker
import atheriz.settings as settings


class TestAsyncThreadPool:
    def test_simple_async_execution(self):
        """Test executing a single async task."""
        atp = AsyncThreadPool(max_threads=2)

        result_event = threading.Event()
        result_data = {}

        async def my_task(key, val):
            result_data[key] = val
            result_event.set()

        atp.add_task(my_task, "test", 123)

        # Wait for task to complete
        assert result_event.wait(timeout=2.0)
        assert result_data["test"] == 123

        atp.stop()

    def test_stress_add_coros(self):
        """Test adding many coroutines rapidly."""
        count = 100
        atp = AsyncThreadPool(max_threads=4)
        lock = threading.Lock()
        counter = 0
        finished_event = threading.Event()

        async def increment_task():
            nonlocal counter
            with lock:
                counter += 1
                if counter == count:
                    finished_event.set()
            # Simulate some work
            await asyncio.sleep(0.001)

        for _ in range(count):
            atp.add_task(increment_task)

        # Wait
        assert finished_event.wait(timeout=5.0)
        with lock:
            assert counter == count

        atp.stop()

    def test_threaded_stress(self):
        """Test adding tasks from multiple threads simultaneously."""
        task_count = 100
        thread_count = 4
        atp = AsyncThreadPool(max_threads=4)
        lock = threading.Lock()
        counter = 0
        finished_event = threading.Event()

        async def increment_task():
            nonlocal counter
            with lock:
                counter += 1
                if counter == task_count * thread_count:
                    finished_event.set()

        def worker():
            for _ in range(task_count):
                atp.add_task(increment_task)

        threads = []
        for _ in range(thread_count):
            t = threading.Thread(target=worker)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        assert finished_event.wait(timeout=5.0)
        with lock:
            assert counter == task_count * thread_count

        atp.stop()

    def test_delay_sync(self):
        """Test delay with a sync function."""
        atp = AsyncThreadPool(max_threads=2)
        result_event = threading.Event()
        result_data = {}

        def my_task(key, val):
            result_data[key] = val
            result_event.set()

        start_time = time.time()
        atp.delay(0.2, my_task, "test_sync", 123)
        
        # Wait for task to complete
        assert result_event.wait(timeout=2.0)
        end_time = time.time()
        
        assert end_time - start_time >= 0.2
        assert result_data["test_sync"] == 123
        atp.stop()

    def test_delay_async(self):
        """Test delay with an async function."""
        atp = AsyncThreadPool(max_threads=2)
        result_event = threading.Event()
        result_data = {}

        async def my_task(key, val):
            result_data[key] = val
            result_event.set()

        start_time = time.time()
        atp.delay(0.2, my_task, "test_async", 456)
        
        # Wait for task to complete
        assert result_event.wait(timeout=2.0)
        end_time = time.time()
        
        assert end_time - start_time >= 0.2
        assert result_data["test_async"] == 456
        atp.stop()

    def test_async_partial(self):
        """A functools.partial of an async function must run on the loop
        (the co_flags check missed partials, dropping the coroutine)."""
        atp = AsyncThreadPool(max_threads=2)
        result_event = threading.Event()
        result_data = {}

        async def my_task(key, val):
            result_data[key] = val
            result_event.set()

        atp.add_task(functools.partial(my_task, "k", "v"))

        assert result_event.wait(timeout=2.0)
        assert result_data["k"] == "v"
        atp.stop()

    def test_stop_timeout_on_stuck_worker(self):
        """stop(wait=True, timeout=N) should return within ~N seconds even if a worker is stuck."""
        atp = AsyncThreadPool(max_threads=2)
        blocker = threading.Event()

        def stuck_task():
            blocker.wait(timeout=30)  # blocks until we release it

        atp.add_task(stuck_task)

        start = time.time()
        atp.stop(wait=True, timeout=1)
        elapsed = time.time() - start

        assert elapsed < 3, f"stop() took {elapsed:.1f}s, expected <3s with timeout=1"
        blocker.set()  # release the stuck thread so it can exit cleanly


class TestAsyncTicker:
    def test_ticker(self):
        """Test that the ticker periodically runs a task."""
        atp = AsyncThreadPool(max_threads=2)
        ticker = AsyncTicker()

        counter = 0
        lock = threading.Lock()

        async def tick_task():
            nonlocal counter
            with lock:
                counter += 1

        # Add task with very short interval
        interval = 0.05
        ticker.add_coro(tick_task, interval)

        # Wait for a few ticks
        time.sleep(0.5)

        with lock:
            current_count = counter

        ticker.stop()
        atp.stop()

        # Should have run at least a few times
        # 0.5s / 0.05s = 10 times theoretically. Check for at least 3 to be safe against lag.
        assert current_count >= 3

    def test_ticker_remove_coro(self):
        """Test removing a coro from the ticker."""
        atp = AsyncThreadPool(max_threads=2)
        ticker = AsyncTicker()

        counter = 0
        lock = threading.Lock()

        async def tick_task():
            nonlocal counter
            with lock:
                counter += 1

        interval = 0.05
        ticker.add_coro(tick_task, interval)
        time.sleep(0.1)  # give it time to start

        # remove it
        ticker.remove_coro(tick_task, interval)
        
        with lock:
            current_count = counter

        time.sleep(0.2)  # wait more

        with lock:
            after_count = counter
            
        ticker.stop()
        atp.stop()

        # Counter shouldn't have incremented more after removal (allowing for 1 delayed tick)
        assert after_count <= current_count + 1

    def test_ticker_clear(self):
        """Test clearing all coros from the ticker."""
        atp = AsyncThreadPool(max_threads=2)
        ticker = AsyncTicker()

        counter1, counter2 = 0, 0
        lock = threading.Lock()

        async def tick_task1():
            nonlocal counter1
            with lock:
                counter1 += 1
                
        async def tick_task2():
            nonlocal counter2
            with lock:
                counter2 += 1

        ticker.add_coro(tick_task1, 0.05)
        ticker.add_coro(tick_task2, 0.1)
        
        time.sleep(0.1)
        
        ticker.clear()
        
        with lock:
            c1, c2 = counter1, counter2
            
        time.sleep(0.2)
        
        with lock:
            c1_after, c2_after = counter1, counter2
            
        atp.stop()

        assert c1_after <= c1 + 1
        assert c2_after <= c2 + 1


class TestAsyncThread:
    def test_stop_uses_event_not_bool(self):
        """Verify AsyncThread uses threading.Event for wait signaling."""
        from atheriz.globals.asyncthreadpool import AsyncThread
        atp = AsyncThreadPool(max_threads=2)
        t = atp.threads[0]
        assert isinstance(t._wait_event, threading.Event)

    def test_stop_wait_true_blocks(self):
        """stop(wait=True) should set the event so run() waits for pending tasks."""
        from atheriz.globals.asyncthreadpool import AsyncThread
        atp = AsyncThreadPool(max_threads=2)
        t = atp.threads[0]
        t.stop(wait=True)
        assert t._wait_event.is_set()

    def test_stop_wait_false_does_not_set(self):
        """stop(wait=False) should not set the wait event."""
        from atheriz.globals.asyncthreadpool import AsyncThread
        atp = AsyncThreadPool(max_threads=2)
        t = atp.threads[0]
        t.stop(wait=False)
        assert not t._wait_event.is_set()


def test_do_shutdown_resets_global_threadpool(global_test_env):
    """A real do_shutdown() must not leave its dead pool as the singleton:
    anything touching the pool afterwards gets a fresh working one."""
    from unittest.mock import MagicMock, patch

    import atheriz.globals.startstop as ss
    from atheriz.globals import get as get_singleton
    from atheriz.globals.asyncthreadpool import AsyncThreadPool
    from atheriz.globals.get import get_async_threadpool

    get_singleton._ASYNC_THREAD_POOL = None
    old_pool = get_async_threadpool()
    assert isinstance(old_pool, AsyncThreadPool)

    with patch.object(ss, "get_server_channel", return_value=None), \
         patch.object(ss, "stop_autosave"), \
         patch("atheriz.server_events", create=True), \
         patch.object(ss, "get_async_ticker", return_value=MagicMock()), \
         patch.object(ss, "get_game_time"), \
         patch.object(ss, "get_database", return_value=MagicMock()), \
         patch.object(ss, "msg_all"), \
         patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
         patch.object(ss.settings, "AUTOSAVE_ON_SHUTDOWN", False):
        ss.do_shutdown()

    # the old pool's workers are gone and the singleton was dropped
    assert not any(t.is_alive() for t in old_pool.threads[1:])
    assert get_singleton._ASYNC_THREAD_POOL is None

    # a fresh pool must be created and actually execute work
    new_pool = get_async_threadpool()
    assert isinstance(new_pool, AsyncThreadPool)
    assert new_pool is not old_pool

    got = []
    new_pool.add_task(lambda: got.append("ok"))
    deadline = time.time() + 3
    while time.time() < deadline and not got:
        time.sleep(0.01)
    assert got == ["ok"]


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


class TestThreadpoolQueue:
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


class TestThreadpoolDrain:
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
            # the queue was full of junk; it now holds sentinels (max_threads-1) plus possibly one leftover junk
            assert atp.task_queue.qsize() == atp.max_threads
            # prove every worker got a sentinel: they all exit after unblock
            block.set()
            for t in atp.threads[1:]:
                t.join(timeout=3)
                assert not t.is_alive(), f"worker {t.name} never received a sentinel"
            # max_threads-1 sentinels went in, workers took them; all junk was discarded or processed
            leftover = []
            while True:
                try:
                    leftover.append(atp.task_queue.get_nowait())
                except queue.Empty:
                    break
            assert leftover == [] or leftover == [None]
        finally:
            block.set()


def test_delay_does_not_resurrect_pool_after_shutdown(global_test_env):
    import atheriz.globals.get as get_mod
    from atheriz.globals.get import get_async_threadpool

    pool = get_async_threadpool()
    calls = []
    orig_add = pool.add_task
    pool.add_task = lambda func, *a, **kw: calls.append((func, a, kw)) or True

    captured = {}

    def fake_submit(coro, target_loop):
        captured["coro"] = coro
        captured["loop"] = target_loop
        return MagicMock()

    with patch("atheriz.globals.asyncthreadpool._submit", side_effect=fake_submit):
        pool.delay(0.1, lambda: None)

    assert "coro" in captured
    coro = captured["coro"]

    pool._stopped = True
    with get_mod._SINGLETON_LOCK:
        saved = get_mod._ASYNC_THREAD_POOL
        get_mod._ASYNC_THREAD_POOL = None

    async def instant_sleep(delay):
        return

    async def run_coro():
        with patch("atheriz.globals.asyncthreadpool.asyncio.sleep", instant_sleep):
            await coro

    tmp_loop = asyncio.new_event_loop()
    try:
        tmp_loop.run_until_complete(run_coro())
    finally:
        tmp_loop.close()

    assert len(calls) == 0, f"add_task called after shutdown: {calls}"
    assert get_mod._ASYNC_THREAD_POOL is None, "delay resurrected pool after shutdown"

    pool.add_task = orig_add
    pool._stopped = False
    with get_mod._SINGLETON_LOCK:
        if get_mod._ASYNC_THREAD_POOL is None:
            get_mod._ASYNC_THREAD_POOL = saved


def test_ticker_clear_while_timer_running():
    import atheriz.globals.get as get_mod
    from atheriz.globals.asyncthreadpool import AsyncTicker, AsyncThreadPool

    old = get_mod._ASYNC_THREAD_POOL
    atp = AsyncThreadPool(max_threads=2)
    get_mod._ASYNC_THREAD_POOL = atp
    ticker = AsyncTicker()
    counter = 0

    async def tick():
        nonlocal counter
        counter += 1

    try:
        ticker.add_coro(tick, 0.05)
        time.sleep(0.12)
        assert 0.05 in ticker.slots
        assert ticker.slots[0.05].running is True
        ticker.clear()
        assert ticker.slots == {}
        before = counter
        time.sleep(0.2)
        assert counter <= before + 1
        ticker.add_coro(tick, 0.05)
        time.sleep(0.08)
        assert counter > before
    finally:
        ticker.clear()
        atp.stop(wait=True, timeout=5)
        get_mod._ASYNC_THREAD_POOL = old
