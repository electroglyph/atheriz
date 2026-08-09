import asyncio
from asyncio import AbstractEventLoop
import inspect
import os
from threading import Thread, RLock, Event
import time
from typing import Optional
import traceback
import queue
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.globals.get import get_async_threadpool


class AsyncThread(Thread):
    def __init__(self, loop: AbstractEventLoop, num: int):
        self.loop = loop
        self.stop_event = asyncio.Event()
        super().__init__(None, daemon=True)
        self.name = f"AsyncThread{num}"
        self._wait_event = Event()

    def run(self):
        self.loop.run_until_complete(self.stop_event.wait())
        if self._wait_event.is_set():
            pending = asyncio.all_tasks(self.loop)
            if pending:
                done, not_done = self.loop.run_until_complete(
                    asyncio.wait(pending, timeout=10)
                )
                if not_done:
                    for task in not_done:
                        task.cancel()
                    self.loop.run_until_complete(
                        asyncio.gather(*not_done, return_exceptions=True)
                    )

    async def do_stop(self):
        self.stop_event.set()

    def stop(self, wait):
        if wait:
            self._wait_event.set()
        asyncio.run_coroutine_threadsafe(self.do_stop(), self.loop)


class AsyncThreadPool:
    def __init__(self, max_threads: Optional[int] = None, default_timeout=None):
        if max_threads == None:
            max_threads = os.cpu_count() or 4
        self.max_threads = max_threads
        self.threads = []
        self.loop = asyncio.new_event_loop()
        self.threads.append(AsyncThread(self.loop, 0))
        self.threads[0].start()  # first thread is for async
        self.timeout = default_timeout
        self.task_queue = queue.Queue(maxsize=settings.THREADPOOL_QUEUE_LIMIT)
        self._last_full_log = 0.0
        for _ in range(max_threads - 1):  # rest of the threads for sync
            t = Thread(daemon=True, target=self._work_loop)
            t.start()
            self.threads.append(t)

    @staticmethod
    def _log_task_error(args):
        tb = traceback.format_exc()
        if settings.DEBUG:
            try:
                caller = args[0]
                caller.msg(f"{tb}")
            except Exception:
                pass
        logger.error(f"{tb}")

    async def _do_async(self, func, *args, **kwargs):
        try:
            await func(*args, **kwargs)
        except Exception:
            self._log_task_error(args)

    def run(self, func, *args, **kwargs):
        """Execute one task with pool semantics: coroutines go to the async
        loop, sync functions run inline on the calling worker. Shared by
        _work_loop and by in-worker dispatch (issue #31)."""
        if inspect.iscoroutinefunction(func):
            asyncio.run_coroutine_threadsafe(self._do_async(func, *args, **kwargs), self.loop)
        else:
            try:
                func(*args, **kwargs)
            except Exception:
                self._log_task_error(args)

    def _work_loop(self):
        while True:
            task = self.task_queue.get()
            if task is None:  # kill signal
                # print("worker thread stopping...")
                break
            func, args, kwargs = task
            self.run(func, *args, **kwargs)

    def stop(self, wait=True, timeout=10):
        """
        Stop AsyncThreadPool. AsyncTicker should be stopped first.
        Args:
            wait (bool, optional): wait for async tasks to finish. Defaults to True.
            timeout (float, optional): seconds to wait for worker threads. Defaults to 10.
        """
        logger.info("at AsyncThreadPool.stop() ...")
        self.threads[0].stop(wait)
        for _ in range(self.max_threads):
            while True:
                try:
                    self.task_queue.put_nowait(None)
                    break
                except queue.Full:
                    # queue flooded (#32): discard the oldest pending task to
                    # make room for the sentinel; shutdown must never block
                    try:
                        self.task_queue.get_nowait()
                    except queue.Empty:
                        break
        if wait:
            for t in self.threads[1:]:
                t.join(timeout=timeout)
                if t.is_alive():
                    logger.warning(f"Thread {t.name} did not stop within {timeout}s")

    def add_task(self, func, *args, **kwargs):
        """
        execute a function on the threadpool
        Args:
            func (callable): coroutine or function to execute
            args: func args
            kwargs: func kwargs
        Returns True when the task was accepted, False when the queue is
        full (newest task rejected; admission never blocks the caller, #32).
        """
        try:
            self.task_queue.put_nowait((func, args, kwargs))
        except queue.Full:
            now = time.monotonic()
            if now - self._last_full_log > 10:
                # throttled so a task flood doesn't cause a logging flood
                self._last_full_log = now
                logger.warning(
                    f"[AsyncThreadPool] task queue full ({self.task_queue.maxsize}); dropping task"
                )
            return False
        return True
        
    def delay(self, delay: float, func, *args, **kwargs):
        """
        execute a function on the threadpool after a delay
        Args:
            delay (float): delay in seconds
            func (callable): function to execute, can be coroutine or function
            args: func args
            kwargs: func kwargs
        """
        async def _delayed_task():
            await asyncio.sleep(delay)
            self.add_task(func, *args, **kwargs)
        asyncio.run_coroutine_threadsafe(_delayed_task(), self.loop)


class AsyncTicker:
    class TimeSlot:
        def __init__(self, interval: float) -> None:
            self.atp = get_async_threadpool()
            self.lock = RLock()
            self.interval = interval
            self.coros = set()
            self.running = False
            self._future = None

        def add_coro(self, coro):
            with self.lock:
                self.coros.add(coro)

        def remove_coro(self, coro):
            with self.lock:
                self.coros.discard(coro)
                if not self.coros:
                    self.running = False
                    if self._future:
                        self._future.cancel()

        def stop(self):
            with self.lock:
                self.running = False
                if self._future:
                    self._future.cancel()

        async def timer(self):
            try:
                while self.running:
                    await asyncio.sleep(self.interval)
                    with self.lock:
                        if not self.running:
                            break
                        batch = list(self.coros)
                    for c in batch:
                        self.atp.add_task(c)
            except asyncio.CancelledError:
                pass

        def start(self):
            with self.lock:
                if not self.running:
                    self.running = True
                    self._future = asyncio.run_coroutine_threadsafe(
                        self.timer(), 
                        self.atp.loop
                    )

    def __init__(self) -> None:
        self.lock = RLock()
        self.slots: dict[float, AsyncTicker.TimeSlot] = {}

    def add_coro(self, coro, interval: float):
        with self.lock:
            slot = self.slots.get(interval)
            if not slot:
                slot = AsyncTicker.TimeSlot(interval)
                slot.add_coro(coro)
                self.slots[interval] = slot
                slot.start()
                return
        slot.add_coro(coro)
        slot.start()

    def remove_coro(self, coro, interval: float):
        with self.lock:
            slot = self.slots.get(interval)
        if slot:
            slot.remove_coro(coro)
                
    def clear(self):
        """
        clear all running tickers
        """
        self.stop()
        with self.lock:
            self.slots.clear()

    def stop(self):
        """
        stop all running tickers
        """
        logger.info("at AsyncTicker.stop() ...")
        with self.lock:
            try:
                for v in self.slots.values():
                    v.stop()
            except:
                pass
