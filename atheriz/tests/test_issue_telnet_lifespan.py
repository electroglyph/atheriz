"""Issue tests: #24 — `TelnetProtocol.setup` does
``app.router.lifespan_context = lifespan`` (telnet.py:144), quietly overwriting
any lifespan installed on the FastAPI app beforehand.

INTENT: mounting the telnet protocol must preserve a previously-installed
lifespan so its startup/shutdown hooks still run.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi import FastAPI

from atheriz.network.telnet import TelnetProtocol


class _ServerStub:
    def __init__(self):
        self._closed = False

    def close(self):
        self._closed = True

    async def wait_closed(self):
        return None


async def _fake_create_server(*args, **kwargs):
    return _ServerStub()


def test_mounting_telnet_preserves_previous_lifespan(global_test_env):
    """INTENT: telnet's lifespan must be composed with an existing one, not
    replace it. Today `app.router.lifespan_context` is overwritten so the
    sentinel lifespan's start/stop hooks never run -> FAIL."""
    app = FastAPI()
    calls = []

    @asynccontextmanager
    async def original(app):
        calls.append("start")
        yield
        calls.append("stop")

    app.router.lifespan_context = original

    with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake_create_server):
        TelnetProtocol.setup(app)

        installed = app.router.lifespan_context

        async def run():
            async with installed(app):
                pass

        asyncio.run(run())

    assert calls == ["start", "stop"], (
        f"the pre-installed lifespan was dropped by {TelnetProtocol.__name__}.setup; calls={calls}"
    )


def test_setup_composes_server_lifecycle_with_previous(global_test_env):
    """INTENT: an existing lifespan keeps running AND the telnet server
    starts/stops inside it; the server task must not be a class attribute
    shared across app instances."""
    app = FastAPI()
    calls = []

    @asynccontextmanager
    async def original(app):
        calls.append("start")
        yield
        calls.append("stop")

    app.router.lifespan_context = original

    with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake_create_server):
        TelnetProtocol.setup(app)

        installed = app.router.lifespan_context

        async def run():
            async with installed(app):
                calls.append("inside")

        asyncio.run(run())

    assert calls == ["start", "inside", "stop"], (
        f"composed lifespan ran out of order; calls={calls}"
    )
    assert not hasattr(TelnetProtocol, "_server_task"), (
        "server task must be per-app (closure), not a class attribute"
    )