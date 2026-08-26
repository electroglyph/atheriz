"""Issue tests: drain-worker double-start race in the connection input queue.

The worker-slot reservation (_input_running) and the threadpool submission
were split across a lock boundary; a rejected add_task unconditionally cleared
the queue and reset the flag, which could spawn a second concurrent drain
worker (breaking per-connection FIFO) and silently discard queued input.
The fix submits under the connection lock and keeps queued input on rejection.
"""

from __future__ import annotations

import threading
import time

import pytest

from atheriz.globals.get import get_async_threadpool
from atheriz.tests.fakes import FakeConnection


def _wait(cond, timeout=5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def pool(global_test_env):
    return get_async_threadpool()


class _DrainRecorder:
    """Tracks concurrent drain executions and handler invocations."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.ran: list = []
        self.started = threading.Event()

    def make_handler(self, tag, delay=0.0, blocker: threading.Event | None = None):
        def handler(conn, args, kwargs):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                self.ran.append(tag)
                self.started.set()
            if delay:
                time.sleep(delay)
            if blocker is not None:
                blocker.wait(5)
            with self.lock:
                self.active -= 1

        return handler


def test_single_worker_invariant_under_rejection(pool, monkeypatch):
    """INTENT: with add_task failing intermittently, at most one drain worker
    ever runs concurrently and every enqueued handler runs exactly once."""
    real_add = pool.add_task
    budget = {"failures": 3}

    def flaky_add(func, *args, **kwargs):
        if budget["failures"] > 0:
            budget["failures"] -= 1
            return False
        return real_add(func, *args, **kwargs)

    monkeypatch.setattr(pool, "add_task", flaky_add)

    conn = FakeConnection()
    rec = _DrainRecorder()
    total = 20
    for i in range(total):
        conn.enqueue_input(rec.make_handler(i), [], {})

    assert _wait(lambda: len(rec.ran) == total)
    assert rec.max_active <= 1
    assert sorted(rec.ran) == list(range(total))


def test_no_silent_loss_on_rejection(pool, monkeypatch):
    """INTENT: input accepted before a rejected submission must survive and
    run (FIFO) once a later enqueue succeeds — nothing is cleared."""
    real_add = pool.add_task
    state = {"reject_next": True}

    def one_shot_reject(func, *args, **kwargs):
        if state["reject_next"]:
            state["reject_next"] = False
            return False
        return real_add(func, *args, **kwargs)

    monkeypatch.setattr(pool, "add_task", one_shot_reject)

    conn = FakeConnection()
    rec = _DrainRecorder()

    conn.enqueue_input(rec.make_handler("A"), [], {})
    assert conn._input_queue, "queue must be kept intact on rejection"
    assert conn._input_running is False
    assert rec.ran == []

    conn.enqueue_input(rec.make_handler("B"), [], {})

    assert _wait(lambda: rec.ran == ["A", "B"])
    assert not conn._input_queue


def test_no_double_start_while_worker_mid_run(pool, monkeypatch):
    """INTENT: while a drain worker is alive, enqueue must never submit a new
    worker; the blocked worker finishes alone and drains everything."""
    calls = {"n": 0}
    calls_lock = threading.Lock()
    real_add = pool.add_task

    def counting_add(func, *args, **kwargs):
        with calls_lock:
            calls["n"] += 1
        return real_add(func, *args, **kwargs)

    monkeypatch.setattr(pool, "add_task", counting_add)

    conn = FakeConnection()
    blocker = threading.Event()
    rec = _DrainRecorder()

    conn.enqueue_input(rec.make_handler("first", blocker=blocker), [], {})
    assert rec.started.wait(2)

    for i in range(5):
        conn.enqueue_input(rec.make_handler(f"later-{i}"), [], {})

    with calls_lock:
        assert calls["n"] == 1

    blocker.set()
    assert _wait(lambda: len(rec.ran) == 6 and not conn._input_running)

    with calls_lock:
        assert calls["n"] == 1
    assert rec.max_active <= 1
    assert rec.ran[0] == "first"
    assert len(rec.ran) == 6


def test_rejection_busy_reply_throttled(pool, monkeypatch):
    """INTENT: repeated rejections notify the client at most once per throttle
    window instead of clearing the queue silently."""
    monkeypatch.setattr(pool, "add_task", lambda *a, **k: False)

    conn = FakeConnection()
    rec = _DrainRecorder()

    for i in range(5):
        conn.enqueue_input(rec.make_handler(i), [], {})

    busy = [m for m in conn.sent if m[0] == "text" and "busy" in str(m[1]).lower()]
    assert len(busy) == 1
    assert len(conn._input_queue) == 5

    monkeypatch.undo()
    conn.enqueue_input(rec.make_handler(99), [], {})
    assert _wait(lambda: len(rec.ran) == 6)


def test_input_queue_retries_after_threadpool_reject_without_new_enqueue(pool, monkeypatch):
    """INTENT: when add_task rejects due to THREADPOOL_QUEUE_LIMIT, pending
    input must be retried automatically without requiring a new enqueue;
    otherwise queue starves with _input_running False and messages stuck."""
    real_add = pool.add_task
    first = {"rejected": True}

    def fail_once(func, *a, **k):
        if first["rejected"]:
            first["rejected"] = False
            return False
        return real_add(func, *a, **k)

    monkeypatch.setattr(pool, "add_task", fail_once)
    conn = FakeConnection()
    rec = _DrainRecorder()
    conn.enqueue_input(rec.make_handler("only"), [], {})
    assert len(conn._input_queue) == 1
    assert conn._input_running is False
    monkeypatch.setattr(pool, "add_task", real_add)
    assert _wait(lambda: rec.ran == ["only"], timeout=1.0), "input queue starved after threadpool reject: handler never retried without new input"
    assert not conn._input_queue
    assert conn._input_running is False
