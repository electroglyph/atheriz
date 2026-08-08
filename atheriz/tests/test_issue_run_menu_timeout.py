"""Issue tests: #28 — `run_menu()` blocks the worker thread on
``asyncio.run_coroutine_threadsafe(...).result()`` with no timeout (menu.py:86-88).
If the session dies without cancelling its `input_future`, the thread is parked
forever.

INTENT: `run_menu()` must not park a worker thread indefinitely even when the
session's prompt never resolves; it gives up after
`settings.MENU_PROMPT_TIMEOUT` (default 60s) and exits cleanly when a
disconnect cancels the pending prompt.
"""
from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

from atheriz.menu import Choice, run_menu
from atheriz.objects.session import Session


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
    blocks on `.result()` with no timeout -> the thread never returns -> FAIL.
    The timeout is lowered from the 60s default so the test stays fast."""
    caller = _DeadCaller()
    with patch("atheriz.menu.settings.MENU_PROMPT_TIMEOUT", 1):
        t = threading.Thread(target=run_menu, args=(caller, _node), daemon=True)
        t.start()
        t.join(timeout=5)
    assert not t.is_alive(), "run_menu() parked a worker thread forever"


def test_run_menu_returns_when_prompt_cancelled(global_test_env):
    """INTENT: a real disconnect cancels the pending prompt future
    (`Session.at_disconnect`); `run_menu()` must exit cleanly instead of
    raising an unhandled `CancelledError` in the worker thread."""
    session = Session(connection=MagicMock())
    session.connection.msg = MagicMock()
    caller = MagicMock()
    caller.session = session
    errors = []

    def target():
        try:
            run_menu(caller, _node)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    for _ in range(500):
        if session.input_future is not None:
            break
        time.sleep(0.01)
    assert session.input_future is not None, "prompt future was never registered"
    session.at_disconnect()
    t.join(timeout=5)
    assert not t.is_alive(), "run_menu() did not exit after prompt cancellation"
    assert errors == [], f"run_menu() raised after cancellation: {errors}"