"""Issue tests: `execute_cmd` is a stub that silently does nothing.

`Object.execute_cmd(raw_string)` should run the command exactly as if the
string had been typed into the object's own session — same command lookup,
aliasing, access control, and async dispatch as the logged-in text handler.
Today it is `pass`, so any caller silently gets nothing.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

from atheriz import settings
from atheriz.objects.nodes import Node
from atheriz.objects.session import Session
from atheriz.tests.fakes import make_object
from atheriz.utils import Coord


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    """Poll `predicate` until it returns truthy (the threadpool runs commands
    asynchronously on a worker thread, so dispatch is fire-and-forget)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _msg_texts(connection) -> list[str]:
    texts = []
    for call in connection.msg.call_args_list:
        if call.args:
            texts.append(str(call.args[0]))
        elif call.kwargs.get("text"):
            texts.append(str(call.kwargs["text"]))
    return texts


def _texts_contain(connection, needle: str) -> bool:
    return any(needle in t for t in _msg_texts(connection))


def _mock_texts(mock) -> list[str]:
    texts = []
    for call in mock.call_args_list:
        if call.args:
            texts.append(str(call.args[0]))
        elif call.kwargs.get("text"):
            texts.append(str(call.kwargs["text"]))
    return texts


def _make_player(session=None):
    puppet = make_object("puppet", is_pc=True, privilege_level=settings.Privilege.Player)
    if session is not None:
        puppet.session = session
    return puppet


class TestExecuteCmd:
    def test_runs_inventory_command(self, global_test_env):
        """INTENT: executing 'inventory' actually runs the command and routes
        its output to the object's session."""
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)

        puppet.execute_cmd("inventory")

        assert _wait_for(lambda: _texts_contain(session.connection, "You are carrying nothing."))

    def test_runs_alias(self, global_test_env):
        """INTENT: command aliases resolve ('i' -> inventory)."""
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)

        puppet.execute_cmd("i")

        assert _wait_for(lambda: _texts_contain(session.connection, "You are carrying nothing."))

    def test_respects_access_gate(self, global_test_env):
        """INTENT: builder-only commands are refused for a plain player."""
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)

        puppet.execute_cmd("build north")

        assert _wait_for(lambda: _texts_contain(session.connection, "You can't do that."))

    def test_unknown_command_falls_to_none(self, global_test_env):
        """INTENT: an unmatched command routes to the 'none' fallback."""
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)

        puppet.execute_cmd("frobnicate")

        assert _wait_for(lambda: _texts_contain(session.connection, "not found"))

    def test_empty_string_is_noop(self, global_test_env):
        """INTENT: an empty string is ignored without error and produces no output."""
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)

        puppet.execute_cmd("")
        time.sleep(0.2)

        assert _msg_texts(session.connection) == []

    def test_say_broadcasts_to_room(self, global_test_env):
        """INTENT: a real command with room effects runs — 'say' reaches the
        speaker's session and the room's other occupants."""
        node = Node(coord=Coord("test", 0, 0, 0), desc="A room.", symbol="#")
        observer = make_object("observer")
        observer.msg = MagicMock()
        observer.move_to(node)
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)
        puppet.move_to(node)
        observer.msg.reset_mock()

        puppet.execute_cmd("say hello there")

        assert _wait_for(lambda: _texts_contain(session.connection, "hello there"))
        assert _wait_for(lambda: any("hello there" in t for t in _mock_texts(observer.msg)))

    def test_external_cmdset_from_location(self, global_test_env):
        """INTENT: commands provided by objects in the player's location are
        reachable through execute_cmd."""
        from atheriz.commands.base_cmd import Command

        class WaveCommand(Command):
            key = "boxwave"
            use_parser = False

            def run(self, caller, args):
                caller.msg("You wave.")

        node = Node(coord=Coord("test", 0, 0, 0), desc="A room.", symbol="#")
        prop = make_object("mystery-box")
        prop.external_cmdset.add(WaveCommand())
        prop.move_to(node)
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)
        puppet.move_to(node)

        puppet.execute_cmd("boxwave")

        assert _wait_for(lambda: _texts_contain(session.connection, "You wave."))

    def test_async_command_runs_on_threadpool_loop(self, global_test_env):
        """INTENT: fire-and-forget dispatch also runs coroutine commands."""
        from atheriz.commands.base_cmd import Command

        class AsyncWaveCommand(Command):
            key = "asyncboxwave"
            use_parser = False

            async def run(self, caller, args):
                await asyncio.sleep(0)
                caller.msg("Async wave.")

        node = Node(coord=Coord("test", 0, 0, 0), desc="A room.", symbol="#")
        prop = make_object("async-box")
        prop.external_cmdset.add(AsyncWaveCommand())
        prop.move_to(node)
        session = Session()
        session.connection = MagicMock()
        puppet = _make_player(session)
        puppet.move_to(node)

        puppet.execute_cmd("asyncboxwave")

        assert _wait_for(lambda: _texts_contain(session.connection, "Async wave."))
