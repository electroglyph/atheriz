"""Issue tests: #28 — `run_menu()` blocks the worker thread on
``asyncio.run_coroutine_threadsafe(...).result()`` with no timeout (menu.py:86-88).
If the session dies without cancelling its `input_future`, the thread is parked
forever.

INTENT: `run_menu()` must not park a worker thread indefinitely even when the
session's prompt never resolves.
"""
from __future__ import annotations

import asyncio
import threading

from atheriz.menu import Choice, run_menu


def _node(ctx):
    return "Choose", [Choice(key="1", desc="one")]


class _DeadSession:
    lock = threading.RLock()
    input_future = None

    async def prompt(self, text: str):
        await asyncio.Event().wait()  # never resolves: the session is dead


class _DeadCaller:
    session = _DeadSession()


def test_run_menu_returns_when_session_is_dead(global_test_env):
    """INTENT: when the session never answers the prompt, `run_menu()` must
    give up (a timeout) instead of parking its worker thread forever. Today it
    blocks on `.result()` with no timeout -> the thread never returns -> FAIL."""
    caller = _DeadCaller()
    t = threading.Thread(target=run_menu, args=(caller, _node), daemon=True)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "run_menu() parked a worker thread forever"