import asyncio
from asyncio import AbstractEventLoop
import os
from threading import Lock, Thread, RLock
import time
from typing import Optional
import traceback
import queue
from atheriz.logger import logger
from atheriz.settings import DEBUG
from atheriz.singletons.get import get_async_threadpool


class AsyncThread(Thread):
    def __init__(self, loop: AbstractEventLoop, num: int):
        self.loop = loop
        self.stop_event = asyncio.Event()
        super().__init__(None, daemon=True)
        self.name = f"AsyncThread{num}"
        self.wait = False

    def run(self):
        self.loop.run_until_complete(self.stop_event.wait())
        # print(f"thread is stopping: {self.name}")
        if self.wait:
            pending = asyncio.all_tasks(self.loop)
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending))
        # self.loop.stop()
        # self.loop.close()

    async def do_stop(self):
        self.stop_event.set()  # gotta set this event from inside this thread

    def stop(self, wait):  # True = wait for shit to finish
        self.wait = wait
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
        self.task_queue = queue.Queue()
        for _ in range(max_threads - 1):  # rest of the threads for sync
            t = Thread(daemon=True, target=self._work_loop)
            t.start()
            self.threads.append(t)

    def _work_loop(self):
        async def do_async(func, *args, **kwargs):
            try:
                await func(*args, **kwargs)
            except Exception as e:
                tb = traceback.format_exc()
                if DEBUG:
                    try:
                        caller = args[0]
                        caller.msg(f"{tb}")
                    except Exception as e2:
                        logger.error(f"Exception while sending exception to caller: {e2}")
                logger.error(f"{tb}")

        while True:
            task = self.task_queue.get()
            if task is None:  # kill signal
                # print("worker thread stopping...")
                break
            func, args, kwargs = task
            if hasattr(func, "__code__") and func.__code__.co_flags & 128 == 128:
                asyncio.run_coroutine_threadsafe(do_async(func, *args, **kwargs), self.loop)
            else:
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    tb = traceback.format_exc()
                    if DEBUG:
                        try:
                            caller = args[0]
                            caller.msg(f"{tb}")
                        except:
                            pass
                    logger.error(f"{tb}")

    def stop(self, wait=True):
        """
        Stop AsyncThreadPool. AsyncTicker should be stopped first.
        Args:
            wait (bool, optional): wait for async tasks to finish. Defaults to True.
        """
        print("at AsyncThreadPool.stop() ...")
        self.threads[0].stop(wait)
        for _ in range(self.max_threads):
            self.task_queue.put(None)

    def add_task(self, func, *args, **kwargs):
        """
        execute a function on the threadpool
        Args:
            func (callable): coroutine or function to execute
            args: func args
            kwargs: func kwargs
        """
        self.task_queue.put((func, args, kwargs))


class AsyncTicker:
    class TimeSlot:
        def __init__(self, interval: float) -> None:
            self.atp = get_async_threadpool()
            self.lock = RLock()
            self.interval = interval
            self.coros = set()
            self.running = False
            self.task = None

        def add_coro(self, coro):
            with self.lock:
                self.coros.add(coro)

        def remove_coro(self, coro):
            with self.lock:
                try:
                    self.coros.remove(coro)
                except:
                    pass

        def stop(self):
            with self.lock:
                self.running = False
                if self.task:
                    self.task.cancel()

        async def timer(self):
            while True:
                with self.lock:
                    if not self.running:
                        return
                    self.task = asyncio.create_task(asyncio.sleep(self.interval))
                await self.task
                with self.lock:
                    for c in self.coros:
                        self.atp.add_task(c)

        def start(self):
            if not self.running:
                self.running = True
                self.atp.add_task(self.timer)

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
            if len(slot.coros) == 0:
                slot.stop()
                
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
        print("at AsyncTicker.stop() ...")
        with self.lock:
            try:
                for v in self.slots.values():
                    v.stop()
            except:
                pass
