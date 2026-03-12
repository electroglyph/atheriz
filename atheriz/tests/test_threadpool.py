import pytest
import time
import threading
import asyncio
from typing import NoReturn
from atheriz.globals.asyncthreadpool import AsyncThreadPool, AsyncTicker


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

