# 11 The AsyncThreadPool

## 11.1 What it is

The `AsyncThreadPool` is Atheriz's core concurrency engine, located at `atheriz/globals/asyncthreadpool.py`. Rather than relying on rigid, single-threaded processing loops, Atheriz executes heavy systems concurrently to ensure the game server never drops client connections or lags during complex operations.

When you boot an Atheriz server, it spins up a designated number of threads based on your server's CPU count (or overridden via `THREADPOOL_LIMIT` in your `settings.py`). 

- The **First Thread** is strictly preserved for running the internal `asyncio` event loop.
- The **Remaining Threads** are worker threads waiting to cleanly execute synchronous Python code pulled from a queue.

## 11.2 Using the Pool (Fire and Forget)

Because retrieving return values from threads requires managing blocking states (which risks slowing down the server), the `AsyncThreadPool` operates strictly on a **"Fire-and-Forget"** mentality.

You send a function into the pool, and the pool guarantees it will execute it as soon as a worker thread becomes available. You do not wait for the function to finish, and you do not receive a return value.

### 11.2.1 How to Queue a Task
First, import the getter to retrieve the global threadpool instance:

```python
from atheriz.globals.get import get_async_threadpool

atp = get_async_threadpool()
```

Then, use `add_task` to pass the function you want to execute, followed immediately by any arguments that function requires.

```python
def calculate_massive_damage(target, amount, element="fire"):
    # This might take a long time to calculate!
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

## 11.3 Error Handling
If a function executed by the threadpool crashes or raises an Exception, it will not crash the threadpool itself. Instead, the `AsyncThreadPool` catches the Exception and logs the traceback to the server log located in the save folder.

Furthermore, if `DEBUG = True` in your `settings.py`, and the first argument (`args[0]`) passed to your function happens to be an object capable of receiving messages (like a standard `Object` or `Connection`), the threadpool will attempt to automatically print the crash traceback directly to that player's screen in-game!

[Table of Contents](./table_of_contents.md) | [Next: 12 API Reference](./12_api_reference.md)
