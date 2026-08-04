"""Issue #31: input handlers run off the protocol event loop, serialized
per connection, one queue crossing per network message."""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import patch

import pytest

import atheriz.network.manager as mgr_module
from atheriz.network.manager import ConnectionManager
from atheriz.tests.fakes import FakeConnection
from atheriz.globals.get import get_async_threadpool


def _wait(cond, timeout=2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def manager(global_test_env):
    mgr_module._CONNECTION_MANAGER = None
    with patch("atheriz.inputfuncs.InputFuncs") as mock_if:
        mock_if.return_value.get_handlers.return_value = {}
        mgr = ConnectionManager()
    yield mgr
    mgr_module._CONNECTION_MANAGER = None


class TestGameBoundary:
    def test_handler_runs_off_caller_thread_once(self, manager):
        """Handler executes on a threadpool worker, not the dispatching
        thread, and exactly once per message."""
        caller_ident = threading.get_ident()
        seen = []

        def handler(c, a, k):
            seen.append(threading.get_ident())

        manager.register_handler("text", handler)
        c = FakeConnection()
        manager.handle_command(c, json.dumps(["text", ["look"], {}]))
        assert _wait(lambda: seen)
        assert seen == [seen[0]]  # exactly one call
        assert seen[0] != caller_ident

    def test_dispatch_returns_promptly_while_handler_blocked(self, manager):
        """The protocol loop is not blocked by a slow handler."""
        release = threading.Event()
        started = threading.Event()

        def handler(c, a, k):
            started.set()
            release.wait(2.0)

        manager.register_handler("text", handler)
        c = FakeConnection()
        t0 = time.monotonic()
        manager.dispatch(c, "text", [], {})
        elapsed = time.monotonic() - t0
        assert started.wait(2.0)
        assert elapsed < 1.0
        release.set()

    def test_per_connection_fifo_ordering(self, manager):
        """Messages from one connection run in order despite multiple workers."""
        got = []
        lock = threading.Lock()

        def handler(c, a, k):
            with lock:
                got.append(a[0])

        manager.register_handler("text", handler)
        c = FakeConnection()
        n = 50
        for i in range(n):
            manager.dispatch(c, "text", [i], {})
        assert _wait(lambda: len(got) == n, timeout=5.0)
        assert got == list(range(n))

    def test_connections_not_serialized_globally(self, manager):
        """A blocked connection does not stall another connection's input."""
        release = threading.Event()
        done_b = threading.Event()

        def slow(c, a, k):
            release.wait(2.0)

        def fast(c, a, k):
            done_b.set()

        manager.register_handler("slow", slow)
        manager.register_handler("fast", fast)
        a, b = FakeConnection("a"), FakeConnection("b")
        manager.dispatch(a, "slow", [], {})
        manager.dispatch(b, "fast", [], {})
        assert done_b.wait(2.0)
        release.set()


class TestDisconnectCleanup:
    def test_disconnect_drops_queued_input(self, manager):
        """Input queued behind a blocked drain is discarded on disconnect."""
        release = threading.Event()
        ran = []

        def first(c, a, k):
            release.wait(2.0)

        def second(c, a, k):
            ran.append("second")

        manager.register_handler("first", first)
        manager.register_handler("second", second)
        c = FakeConnection()
        manager.register_connection("c1", c)
        manager.dispatch(c, "first", [], {})
        manager.dispatch(c, "second", [], {})
        manager.disconnect(c)
        release.set()
        # give the drain time to wake and observe the cleared queue
        assert _wait(lambda: not c._input_running)
        time.sleep(0.05)
        assert ran == []


class TestConnectionInputCap:
    def test_flood_capped_newest_dropped_busy_throttled(self, manager):
        """#32: pending input per connection is capped; accepted messages
        still run FIFO; the newest overflow is dropped; the busy reply is
        throttled to one per interval."""
        import atheriz.settings as settings

        release = threading.Event()
        started = threading.Event()
        ran = []

        def first(c, a, k):
            started.set()
            release.wait(5)

        def seq(c, a, k):
            ran.append(a[0])

        manager.register_handler("first", first)
        manager.register_handler("seq", seq)
        c = FakeConnection("cap")
        manager.dispatch(c, "first", [], {})
        assert started.wait(2)
        cap = settings.CONNECTION_INPUT_QUEUE_LIMIT
        for i in range(cap + 50):
            manager.dispatch(c, "seq", [i], {})
        assert len(c._input_queue) == cap
        busy = [m for m in c.sent if m[0] == "text" and "busy" in str(m[1]).lower()]
        assert len(busy) == 1
        release.set()
        assert _wait(lambda: len(ran) == cap, timeout=5)
        assert ran == list(range(cap))

    def test_recovers_after_drain(self, manager):
        """After the drain catches up, the connection accepts input again."""
        import atheriz.settings as settings

        release = threading.Event()
        started = threading.Event()
        ran = []

        def first(c, a, k):
            started.set()
            release.wait(5)

        manager.register_handler("first", first)
        manager.register_handler("seq", lambda c, a, k: ran.append(a[0]))
        c = FakeConnection("cap2")
        manager.dispatch(c, "first", [], {})
        assert started.wait(2)
        for i in range(settings.CONNECTION_INPUT_QUEUE_LIMIT + 10):
            manager.dispatch(c, "seq", [i], {})
        release.set()
        assert _wait(lambda: not c._input_running and len(ran) == settings.CONNECTION_INPUT_QUEUE_LIMIT, timeout=5)
        manager.dispatch(c, "seq", ["after"], {})
        assert _wait(lambda: ran[-1:] == ["after"])


class TestThreadpoolAPI:

    def test_run_matches_pool_semantics(self, global_test_env):
        """run() executes sync inline and logs exceptions without raising."""
        atp = get_async_threadpool()
        got = []
        atp.run(got.append, 1)
        assert got == [1]
        atp.run(lambda: 1 / 0)  # must not raise out of run()
