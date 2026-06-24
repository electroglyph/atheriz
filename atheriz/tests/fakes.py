from __future__ import annotations
"""Shared test fakes and helpers used across the atheriz test suite.

Importable as `atheriz.tests.fakes`. Centralizes the stand-in classes that
used to be duplicated in test_channel.py, test_build_command.py,
test_menu.py, test_search.py, etc.
"""

import asyncio
from unittest.mock import MagicMock
from typing import Any, Callable

from atheriz.network.connection import BaseConnection


# ---------------------------------------------------------------------------
# Connection / Session fakes
# ---------------------------------------------------------------------------


class FakeConnection(BaseConnection):
    """A BaseConnection subclass that records every send_command call.

    Useful in place of a real WebSocket or Telnet connection.

    Attributes:
        sent: list of (cmd, args, kwargs) tuples, in order, that were passed
            to `send_command`.
    """

    def __init__(self, session_id: str | None = "test_conn", session=None):
        # Don't call super().__init__ because it creates a real Session and
        # tries to grab a running event loop; tests may run off-loop.
        self.session_id = session_id
        from atheriz.objects.session import Session

        self.session = session if session is not None else Session(connection=self)
        try:
            import asyncio as _asyncio
            self.loop = _asyncio.get_running_loop()
        except RuntimeError:
            import asyncio as _asyncio
            self.loop = _asyncio.new_event_loop()
        import threading as _threading
        self.thread_id = _threading.get_ident()
        import threading as _threading
        self.lock = _threading.RLock()
        self.failed_login_attempts = 0
        self.sent: list[tuple] = []
        self.closed = False

    def send_command(self, cmd, *args, **kwargs):
        self.sent.append((cmd, list(args), dict(kwargs)))

    def close(self):
        self.closed = True
        self.sent.append(("__closed__", [], {}))


class FakeSession:
    """A lightweight stand-in for atheriz.objects.session.Session.

    Records every call to `msg`, `prompt`, and `at_disconnect`. The optional
    `prompt_responses` iterator feeds async `prompt()` replies.
    """

    def __init__(
        self,
        screenreader: bool = False,
        term_width: int = 80,
        term_height: int = 24,
        puppet: Any = None,
        account: Any = None,
        prompt_responses: list | None = None,
    ):
        self.account = account
        self.connection = None
        self.puppet = puppet
        self.last_puppet = None
        self.term_width = term_width
        self.term_height = term_height
        self.map_width = 0
        self.map_height = 0
        self.screenreader = screenreader
        self.conn_time = 0.0
        self.cmd_last = None
        self.cmd_total = 0
        self.last_cmd = ""
        self.input_future: asyncio.Future | None = None
        self.at_disconnect = MagicMock()
        self.msgs: list[tuple] = []
        self.prompts: list[str] = []
        self._prompt_iter = iter(prompt_responses or [])

    def msg(self, *args, **kwargs):
        self.msgs.append((args, kwargs))

    async def prompt(self, text: str) -> str:
        self.prompts.append(text)
        return next(self._prompt_iter)


# ---------------------------------------------------------------------------
# Argparse-namespace / caller fakes
# ---------------------------------------------------------------------------


class MockArgs:
    """A stand-in for an argparse.Namespace.

    Stores arbitrary kwargs as attributes. Provides a sensible default for
    every attribute accessed during command runs.
    """

    _DEFAULTS = {
        "list": False,
        "channel": None,
        "unsubscribe": False,
        "subscribe": False,
        "replay": False,
        "message": None,
        "target": None,
        "cmdstring": "",
    }

    def __init__(self, **kwargs):
        for k, v in self._DEFAULTS.items():
            setattr(self, k, kwargs.pop(k, v))
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        d = {k: v for k, v in vars(self).items() if not k.startswith("_")}
        return f"MockArgs({d})"


def make_args(**kwargs) -> MockArgs:
    """Convenience wrapper around MockArgs."""
    return MockArgs(**kwargs)


class MockCaller:
    """A minimal stand-in for a player/account Object.

    Records every call to `msg`, `subscribe`, `unsubscribe`. Has a `name`
    and an optional `location`.
    """

    def __init__(
        self,
        name: str = "TestPlayer",
        location: Any = None,
        is_builder: bool = False,
    ):
        self.name = name
        self.id = -1
        self.location = location
        self.is_builder = is_builder
        self.msg = MagicMock()
        self.subscribe = MagicMock()
        self.unsubscribe = MagicMock()


# ---------------------------------------------------------------------------
# Object factory
# ---------------------------------------------------------------------------


def make_object(name: str = "foo", **attrs) -> Any:
    """Create and register a real Object, then set attributes from `attrs`.

    Saves the most-typed line in command tests.
    """
    from atheriz.objects.base_obj import Object

    obj = Object.create(None, name)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj
