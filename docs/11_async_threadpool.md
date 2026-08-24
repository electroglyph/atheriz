# 11 The AsyncThreadPool

## 11.1 What it is

The `AsyncThreadPool` is Atheriz's core concurrency engine, located at `atheriz/globals/asyncthreadpool.py`. Rather than relying on rigid, single-threaded processing loops, Atheriz executes heavy systems concurrently to ensure the game server never drops client connections or lags during complex operations.

When you boot a server it spins up threads based on `THREADPOOL_LIMIT` (default `os.cpu_count()`, `atheriz/settings.py:71`).

- The **First Thread** runs the `asyncio` event loop (`atheriz/globals/asyncthreadpool.py:84`).
- The **Remaining Threads** are workers pulling from a bounded queue.
- **Relief workers** spawn if queue depth exceeds `THREADPOOL_RELIEF_LIMIT` (`settings.py:73`, `RELIEF_SPAWN_COOLDOWN` `asyncthreadpool.py:69`, `_maybe_spawn_relief_worker:222`).
- **Watchdog** logs starvation if tasks stall `THREADPOOL_WATCHDOG_SECONDS`/`INTERVAL` (`settings.py:75`, `asyncthreadpool.py:251`).

## 11.2 Using the Pool (Fire and Forget)

Because retrieving return values would block, the pool is fire-and-forget — but `add_task(func, *args, **kwargs) -> bool` (`asyncthreadpool.py:339`) returns whether the task was accepted. If the bounded queue (`THREADPOOL_QUEUE_LIMIT=10000`, `settings.py:79`) is full it returns `False` (dropped, throttled log via `_last_full_log`, `112`). Callers like `GameTime.on_tick` (`atheriz/globals/time.py:228`) and `Connection.enqueue_input` check this. You still don't await results, but check the bool for back-pressure.

### 11.2.1 How to Queue a Task
First, import the getter to retrieve the global threadpool instance:

```python
from atheriz.globals.get import get_async_threadpool

atp = get_async_threadpool()
```

Then, use `add_task` to pass the function you want to execute, followed immediately by any arguments that function requires.

```python
def calculate_massive_damage(target, amount, element="fire"):
    target.health -= amount
    print(f"{target.name} took {amount} {element} damage.")

# Inside your command or combat script:
atp = get_async_threadpool()

# Queue it up! (function, args..., kwargs...)
atp.add_task(calculate_massive_damage, my_target, 500, element="ice")
```

### 11.2.2 Async vs Sync Execution
The `AsyncThreadPool` is smart enough to detect whether you are passing a standard function or an `async` coroutine.

If you pass a synchronous function (like the example above), it is handed to one of the open worker threads.

If you pass an `async def` coroutine, the server automatically routes it to the designated asyncio loop thread and schedules it safely using `asyncio.run_coroutine_threadsafe`.

### 11.2.3 Delayed Tasks
`delay(delay, func, *args, **kwargs)` (`asyncthreadpool.py:370`) sleeps `delay` via `await asyncio.sleep` on the loop thread (`_submit` + `_delayed_task`) then `add_task`s the target; supports sync and `async def` coroutines. Returns `None`.

## 11.3 Error Handling
If a pooled function raises, the pool catches, logs via `logger.error` (throttled to 10 s `_last_full_log` `112`), and if `DEBUG=True` and `args[0]` is an `Object`/`Connection` it `msg`s the traceback to that player (`asyncthreadpool.py:158`). Watchdog also logs starvation via `_log_starvation:278`.

[Table of Contents](./table_of_contents.md) | [Next: 12 The Webclient](./12_webclient.md)
