import asyncio
from asyncio import AbstractEventLoop
import inspect
import os
from threading import Thread, RLock, Event
import threading
import time
from typing import Optional
import traceback
import queue
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.globals.get import get_async_threadpool

if os.name == "nt":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass


def _submit(coro, loop):
    """Schedule coro on loop and return its future; close it if submission
    fails (e.g. dead or closed loop) so a failed dispatch never leaks an
    un-awaited coroutine."""
    try:
        return asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        coro.close()
        raise


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
            try:
                pending = asyncio.all_tasks(self.loop)  # type: ignore[call-arg]
            except TypeError:
                pending = asyncio.all_tasks()
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
        self.loop.close()

    async def do_stop(self):
        self.stop_event.set()

    def stop(self, wait):
        if wait:
            self._wait_event.set()
        _submit(self.do_stop(), self.loop)


class AsyncThreadPool:
    """Bounded worker pool for sync tasks (coroutines go to the event loop).

    Concurrency contract: a task must NEVER block waiting for another task
    queued on this pool. Workers are fixed and execute tasks inline, so
    wait-for-result patterns across pool tasks can starve the pool (every
    worker blocked on work that is still queued = permanent deadlock). Use
    coroutines on the shared loop when one unit of work needs another's
    result. Elastic relief workers (below) soften transient saturation but do
    not make blocking-on-pool safe.

    Starvation mitigations:
    - Relief workers: temporary daemon threads spawned when the queue holds
      work while every fixed worker is busy; they exit once the queue drains.
    - Watchdog: logs a throttled starvation warning with diagnostics when the
      pool stays saturated past settings.THREADPOOL_WATCHDOG_SECONDS.
    """

    RELIEF_SPAWN_COOLDOWN = 1.0

    def __init__(self, max_threads: Optional[int] = None, default_timeout=None):
        if max_threads == None:
            max_threads = os.cpu_count() or 4
        self.max_threads = max_threads
        self.threads = []
        if os.name == "nt":
            try:
                self.loop = asyncio.SelectorEventLoop()
            except Exception:
                self.loop = asyncio.new_event_loop()
        else:
            self.loop = asyncio.new_event_loop()
        self.threads.append(AsyncThread(self.loop, 0))
        self.threads[0].start()  # first thread is for async
        self.timeout = default_timeout
        self.task_queue = queue.Queue(maxsize=settings.THREADPOOL_QUEUE_LIMIT)
        self._last_full_log = 0.0
        self._stopped = False
        self._busy = 0
        self._busy_lock = RLock()
        self._relief_count = 0
        self._last_relief_spawn = 0.0
        self._current_tasks = {}
        self._saturated_since: Optional[float] = None
        self._last_starvation_log = 0.0
        self._relief_seq = 0
        self._relief_threads = []
        self._watchdog = Thread(
            daemon=True,
            target=self._watchdog_loop,
            name="AsyncThreadPoolWatchdog",
        )
        self._watchdog.start()
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
            _submit(self._do_async(func, *args, **kwargs), self.loop)
        else:
            try:
                func(*args, **kwargs)
            except Exception:
                self._log_task_error(args)

    def _work_loop(self, relief: bool = False):
        """Worker body. Fixed workers (relief=False) run until a sentinel;
        relief workers re-queue any sentinel they pull so fixed workers always
        receive theirs, retiring on a sentinel once stopped or when the queue
        drains."""
        while True:
            if relief:
                with self._busy_lock:
                    stopped = self._stopped
                if stopped and self.task_queue.qsize() == 0:
                    with self._busy_lock:
                        self._relief_count -= 1
                    return
                try:
                    task = self.task_queue.get(timeout=0.5)
                except queue.Empty:
                    if self.task_queue.qsize() == 0:
                        # queue drained; temporary worker retires
                        with self._busy_lock:
                            self._relief_count -= 1
                        return
                    continue
            else:
                task = self.task_queue.get()
            if task is None:  # kill signal
                if relief:
                    try:
                        self.task_queue.put_nowait(None)
                    except queue.Full:
                        try:
                            self.task_queue.get_nowait()
                            self.task_queue.put_nowait(None)
                        except (queue.Empty, queue.Full):
                            logger.warning("[AsyncThreadPool] relief failed to re-queue sentinel; queue full")
                    with self._busy_lock:
                        if self._stopped:
                            self._relief_count -= 1
                            return
                    time.sleep(0.05)
                    continue
                break
            try:
                func, args, kwargs = task
                name = getattr(func, "__name__", repr(func))
                ident = threading.get_ident()
                started = time.monotonic()
                with self._busy_lock:
                    self._busy += 1
                    self._current_tasks[ident] = (name, started)
                try:
                    self.run(func, *args, **kwargs)
                finally:
                    with self._busy_lock:
                        self._busy -= 1
                        self._current_tasks.pop(ident, None)
            except Exception:
                logger.error(
                    f"[AsyncThreadPool] worker dispatch failed:\n{traceback.format_exc()}"
                )

    def _maybe_spawn_relief_worker(self):
        now = time.monotonic()
        spawn = False
        limit = getattr(settings, "THREADPOOL_RELIEF_LIMIT", 0) or 0
        with self._busy_lock:
            if (
                not self._stopped
                and limit > 0
                and self._relief_count < limit
                and self._busy >= self.max_threads - 1
                and self.task_queue.qsize() > 0
                and now - self._last_relief_spawn >= self.RELIEF_SPAWN_COOLDOWN
            ):
                self._relief_count += 1
                self._relief_seq += 1
                self._last_relief_spawn = now
                seq = self._relief_seq
                spawn = True
        if spawn:
            t = Thread(
                daemon=True,
                target=self._work_loop,
                kwargs={"relief": True},
                name=f"AsyncThreadPoolRelief-{seq}",
            )
            with self._busy_lock:
                self._relief_threads.append(t)
            t.start()

    def _watchdog_loop(self):
        interval = getattr(settings, "THREADPOOL_WATCHDOG_INTERVAL", 5.0) or 5.0
        threshold = getattr(settings, "THREADPOOL_WATCHDOG_SECONDS", 30.0) or 30.0
        while True:
            time.sleep(interval)
            with self._busy_lock:
                stopped = self._stopped
                busy = self._busy
            if stopped:
                return
            qsize = self.task_queue.qsize()
            saturated = qsize > 0 and (
                busy >= self.max_threads - 1 or qsize >= self.task_queue.maxsize
            )
            now = time.monotonic()
            if saturated:
                if self._saturated_since is None:
                    self._saturated_since = now
                elif (
                    now - self._saturated_since >= threshold
                    and now - self._last_starvation_log >= threshold
                ):
                    self._log_starvation(qsize, busy, now - self._saturated_since)
                    self._last_starvation_log = now
            else:
                self._saturated_since = None

    def _log_starvation(self, qsize: int, busy: int, duration: float):
        with self._busy_lock:
            tasks = dict(self._current_tasks)
        now = time.monotonic()
        detail = ", ".join(
            f"{name} running {now - started:.1f}s"
            for _ident, (name, started) in sorted(tasks.items())
        )
        logger.error(
            f"[AsyncThreadPool] starvation suspected: {qsize} task(s) queued, "
            f"{busy}/{self.max_threads - 1} workers busy for {duration:.1f}s; "
            f"running: [{detail}]"
        )

    def stop(self, wait=True, timeout=10):
        """
        Stop AsyncThreadPool. AsyncTicker should be stopped first.
        Args:
            wait (bool, optional): wait for async tasks to finish. Defaults to True.
            timeout (float, optional): seconds to wait for worker threads. Defaults to 10.
        """
        with self._busy_lock:
            self._stopped = True
        logger.info("at AsyncThreadPool.stop() ...")
        try:
            self.threads[0].stop(wait)
        except Exception:
            # dead or closed loop: keep going so sync workers still get
            # their sentinels instead of aborting the whole shutdown
            logger.warning(
                f"[AsyncThreadPool] async thread stop failed:\n{traceback.format_exc()}"
            )
        for _ in range(self.max_threads - 1):
            try:
                self.task_queue.put_nowait(None)
            except queue.Full:
                try:
                    self.task_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.task_queue.put_nowait(None)
                except queue.Full:
                    logger.warning("[AsyncThreadPool] stop failed to enqueue sentinel; queue still full")
        if wait:
            for t in self.threads[1:]:
                t.join(timeout=timeout)
                if t.is_alive():
                    logger.warning(f"Thread {t.name} did not stop within {timeout}s")
            with self._busy_lock:
                relief_snapshot = list(self._relief_threads)
            for t in relief_snapshot:
                t.join(timeout=1)
            with self._busy_lock:
                self._relief_threads = [t for t in self._relief_threads if t.is_alive()]
            self.threads[0].join(timeout=timeout)
            if self.threads[0].is_alive():
                logger.warning(
                    f"Thread {self.threads[0].name} did not stop within {timeout}s"
                )

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
        with self._busy_lock:
            if self._stopped:
                now = time.monotonic()
                if now - self._last_full_log > 10:
                    self._last_full_log = now
                    logger.warning("[AsyncThreadPool] task submitted after stop; discarded")
                return False
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
        self._maybe_spawn_relief_worker()
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
        try:
            pool = get_async_threadpool()
            loop = pool.loop
        except Exception:
            return

        async def _delayed_task():
            await asyncio.sleep(delay)
            try:
                import atheriz.globals.get as get_mod

                if getattr(pool, "_stopped", False):
                    return
                if get_mod._ASYNC_THREAD_POOL is None or get_mod._ASYNC_THREAD_POOL is not pool:
                    return
                pool.add_task(func, *args, **kwargs)
            except Exception:
                pass

        _submit(_delayed_task(), loop)


class AsyncTicker:
    class TimeSlot:
        def __init__(self, interval: float) -> None:
            self.lock = RLock()
            self.interval = interval
            self.coros = set()
            self.pending = set()
            self.running = False
            self._future = None

        def add_coro(self, coro):
            with self.lock:
                self.coros.add(coro)

        def remove_coro(self, coro):
            with self.lock:
                self.coros.discard(coro)
                self.pending.discard(coro)
                if not self.coros:
                    self.running = False
                    if self._future:
                        self._future.cancel()

        def stop(self):
            with self.lock:
                self.running = False
                if self._future:
                    self._future.cancel()

        def _release(self, coro):
            with self.lock:
                self.pending.discard(coro)

        def _tick_once(self, coro):
            atp = get_async_threadpool()
            if inspect.iscoroutinefunction(coro):
                # submit through the helper so a failed dispatch closes the
                # wrapped coroutine instead of leaking it; release the pending
                # guard either way so the coro keeps getting ticked
                try:
                    future = _submit(atp._do_async(coro), atp.loop)
                except Exception:
                    self._release(coro)
                    raise
                future.add_done_callback(lambda _f: self._release(coro))
            else:
                try:
                    coro()
                finally:
                    self._release(coro)

        async def timer(self):
            loop = asyncio.get_running_loop()
            next_tick = loop.time() + self.interval
            try:
                while self.running:
                    delay = next_tick - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    elif delay < -self.interval:
                        next_tick = loop.time()
                    with self.lock:
                        if not self.running:
                            break
                        batch = [c for c in self.coros if c not in self.pending]
                        self.pending.update(batch)
                    for c in batch:
                        with self.lock:
                            if c not in self.coros:
                                # removed between snapshot and dispatch
                                self.pending.discard(c)
                                continue
                        atp = get_async_threadpool()
                        if not atp.add_task(self._tick_once, c):
                            self._release(c)
                    next_tick += self.interval
            except asyncio.CancelledError:
                pass

        def start(self):
            atp = get_async_threadpool()
            with self.lock:
                if not self.running:
                    self.running = True
                    try:
                        self._future = _submit(self.timer(), atp.loop)
                    except Exception:
                        # submission failed (dead loop); don't leave the slot
                        # claiming to run with no timer behind it
                        self.running = False
                        raise

    def __init__(self) -> None:
        self.lock = RLock()
        self.slots: dict[float, AsyncTicker.TimeSlot] = {}

    def add_coro(self, coro, interval: float):
        with self.lock:
            slot = self.slots.get(interval)
            if slot is None:
                slot = AsyncTicker.TimeSlot(interval)
                self.slots[interval] = slot
            slot.add_coro(coro)
            slot.start()

    def remove_coro(self, coro, interval: float):
        with self.lock:
            slot = self.slots.get(interval)
            if slot:
                slot.remove_coro(coro)
                
    def clear(self):
        with self.lock:
            self.stop()
            self.slots.clear()

    def stop(self):
        """
        stop all running tickers
        """
        logger.info("at AsyncTicker.stop() ...")
        with self.lock:
            for v in self.slots.values():
                try:
                    v.stop()
                except Exception:
                    logger.error(
                        f"Error stopping ticker slot {v.interval}:\n{traceback.format_exc()}"
                    )
