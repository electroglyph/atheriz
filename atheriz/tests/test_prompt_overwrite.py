"""Issue tests: `Session.prompt` overwrites `self.input_future`, so a second
concurrent prompt leaves the first awaiter hanging forever.

`prompt()` stores the future in a single attribute; a second call replaces it
before the first is resolved, orphaning the first awaiter. Fixing this
requires not clobbering an in-flight future.
"""
from __future__ import annotations

import asyncio
import concurrent.futures

import pytest

from atheriz.tests.fakes import FakeConnection


class TestPrompt:
    def test_concurrent_prompts_both_resolve(self, running_loop):
        """INTENT: when two `prompt()` calls overlap, resolving the most
        recent one must not orphan the earlier awaiter."""
        conn = FakeConnection()
        session = conn.session

        async def scenario():
            first = asyncio.create_task(session.prompt("first"))
            await asyncio.sleep(0)
            second = asyncio.create_task(session.prompt("second"))
            await asyncio.sleep(0)
            session.input_future.set_result("answer")
            assert await asyncio.wait_for(second, timeout=1) == "answer"
            await asyncio.wait_for(first, timeout=1)
            return True

        fut = asyncio.run_coroutine_threadsafe(scenario(), running_loop)
        try:
            assert fut.result(timeout=5) is True
        except TimeoutError:
            fut.cancel()
            try:
                fut.result(timeout=2)
            except (concurrent.futures.CancelledError, TimeoutError):
                pass
            pytest.fail(
                "first prompt() never resolves after a second prompt() overwrote input_future"
            )
