"""Tests for atheriz.commands.base_cmd — Command base class and parser."""
from __future__ import annotations

import argparse
import asyncio
import copy
import pickle
import shlex
import time
from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.base_cmd import Command, CommandError, GameArgumentParser
from atheriz.objects.nodes import Node
from atheriz.objects.session import Session
from atheriz.tests.fakes import make_object
from atheriz.utils import Coord


class ConcreteCommand(Command):
    """Subclass for testing — adds a couple of arguments."""

    key = "test"
    aliases = ["t", "tst"]
    desc = "A test command"
    extra_desc = "extra info"
    category = "Testing"

    def setup_parser(self):
        self.parser.add_argument("target", help="Target object")
        self.parser.add_argument("-f", "--flag", action="store_true")


class OptionalArgsCommand(Command):
    """Command with no required args — empty input parses cleanly."""

    key = "opt"
    aliases = ["o"]
    desc = "Optional args command"

    def setup_parser(self):
        self.parser.add_argument("-f", "--flag", action="store_true")
        self.parser.add_argument("--name", default="anon")


class NoParserCommand(Command):
    key = "raw"
    use_parser = False


class TestCommandError:
    def test_is_exception(self):
        assert issubclass(CommandError, Exception)

    def test_can_be_raised(self):
        with pytest.raises(CommandError, match="bad arg"):
            raise CommandError("bad arg")

    def test_message_preserved(self):
        e = CommandError("nope")
        assert str(e) == "nope"


class TestGameArgumentParser:
    def test_creates_with_prog_and_desc(self):
        p = GameArgumentParser(prog="foo", description="Foo command")
        assert p.prog == "foo"
        assert p.description == "Foo command"

    def test_error_raises(self):
        p = GameArgumentParser(prog="x")
        with pytest.raises(CommandError, match="bad"):
            p.error("bad")

    def test_print_help_raises(self):
        p = GameArgumentParser(prog="x", description="d")
        with pytest.raises(CommandError) as exc:
            p.print_help()
        # Should contain help text
        assert "usage:" in str(exc.value).lower() or "options:" in str(exc.value).lower()

    def test_print_usage_raises(self):
        p = GameArgumentParser(prog="x")
        with pytest.raises(CommandError) as exc:
            p.print_usage()
        assert "usage:" in str(exc.value).lower()

    def test_exit_raises_with_message(self):
        p = GameArgumentParser(prog="x")
        with pytest.raises(CommandError, match="oops"):
            p.exit(0, "oops")

    def test_exit_no_message_does_not_raise(self):
        p = GameArgumentParser(prog="x")
        # exit() with no message should NOT raise
        p.exit(0)  # should be silent

    def test_normal_parse_still_works(self):
        p = GameArgumentParser(prog="x")
        p.add_argument("name")
        ns = p.parse_args(["alice"])
        assert ns.name == "alice"


class TestCommandClassAttrs:
    def test_defaults(self):
        assert Command.key == "base"
        assert Command.aliases == []
        assert Command.desc == "Base command"
        assert Command.extra_desc == ""
        assert Command.category == "General"
        assert Command.tag == ""
        assert Command.hide is False
        assert Command.use_parser is True

    def test_init_sets_parser_none(self):
        c = Command()
        assert c._parser is None

    def test_init_no_side_effects(self):
        # Lazy parser: __init__ should NOT create the parser
        c = Command()
        assert c._parser is None
        # The parser is created only on first .parser access
        assert isinstance(c.parser, GameArgumentParser)

    def test_access_returns_true(self):
        c = Command()
        assert c.access(MagicMock()) is True

    def test_run_is_noop(self):
        c = Command()
        # Should not raise and returns None
        assert c.run(MagicMock(), "anything") is None


class TestCommandParser:
    def test_parser_lazy(self):
        c = ConcreteCommand()
        assert c._parser is None
        p = c.parser
        assert isinstance(p, GameArgumentParser)
        assert p.prog == "test"
        # Second access returns same instance
        assert c.parser is p

    def test_parser_setter(self):
        c = ConcreteCommand()
        custom = GameArgumentParser(prog="custom")
        c.parser = custom
        assert c.parser is custom

    def test_setup_parser_called(self):
        # Verify setup_parser was called by checking the parser has the args we defined
        c = ConcreteCommand()
        p = c.parser
        # ConcreteCommand defines "target" and "-f/--flag"
        # Get _actions to inspect
        actions = {a.dest for a in p._actions}
        assert "target" in actions
        assert "flag" in actions

    def test_use_parser_false_parser_is_none(self):
        c = NoParserCommand()
        assert c._parser is None
        # The parser property returns None for use_parser=False
        assert c.parser is None

    def test_use_parser_false_parser_setter_works(self):
        c = NoParserCommand()
        c.parser = "anything"
        assert c._parser == "anything"


class TestPrintHelp:
    def test_includes_prog(self):
        c = ConcreteCommand()
        h = c.print_help()
        assert "test" in h

    def test_includes_description(self):
        c = ConcreteCommand()
        h = c.print_help()
        assert "A test command" in h

    def test_includes_aliases_line(self):
        c = ConcreteCommand()
        h = c.print_help()
        assert "aliases:" in h
        assert "test" in h
        assert "t" in h
        assert "tst" in h

    def test_includes_extra_desc(self):
        c = ConcreteCommand()
        h = c.print_help()
        assert "extra info" in h

    def test_no_aliases_still_works(self):
        class NoAliasCommand(Command):
            key = "x"

        c = NoAliasCommand()
        h = c.print_help()
        assert "aliases: x" in h

    def test_empty_extra_desc(self):
        c = Command()
        h = c.print_help()
        # Should not include "extra info" or anything extra
        assert "extra" not in h.lower() or "extra_desc" not in h


class TestExecute:
    def test_use_parser_false_returns_raw_args(self):
        c = NoParserCommand()
        caller = MagicMock()
        run_fn, c_arg, args = c.execute(caller, "any string at all")
        # Bound method identity: compare underlying functions
        assert run_fn.__func__ is c.run.__func__
        assert c_arg is caller
        assert args == "any string at all"
        # Should NOT have called msg (no parser = no help)
        caller.msg.assert_not_called()

    def test_with_empty_args_optional(self):
        c = OptionalArgsCommand()
        caller = MagicMock()
        run_fn, c_arg, parsed = c.execute(caller, "", cmdstring="opt")
        # Empty args: arg_list = [], parses OK
        assert run_fn.__func__ is c.run.__func__
        assert c_arg is caller
        assert parsed.flag is False
        assert parsed.name == "anon"
        caller.msg.assert_not_called()

    def test_with_required_arg_omitted(self):
        c = ConcreteCommand()
        caller = MagicMock()
        # target is required; omit it
        run_fn, c_arg, parsed = c.execute(caller, "", cmdstring="test")
        # Should have sent help text to caller
        caller.msg.assert_called_once()
        help_text = caller.msg.call_args[0][0]
        assert "aliases:" in help_text
        # And returned None tuple
        assert run_fn is None
        assert c_arg is None
        assert parsed is None

    def test_with_positional_arg(self):
        c = ConcreteCommand()
        caller = MagicMock()
        run_fn, c_arg, parsed = c.execute(caller, "alice", cmdstring="test")
        assert run_fn.__func__ is c.run.__func__
        assert c_arg is caller
        assert parsed.target == "alice"
        assert parsed.flag is False
        assert parsed.cmdstring == "test"

    def test_with_flag(self):
        c = ConcreteCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "--flag alice", cmdstring="test")
        assert parsed.flag is True
        assert parsed.target == "alice"

    def test_with_short_flag(self):
        c = ConcreteCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "-f bob", cmdstring="test")
        assert parsed.flag is True
        assert parsed.target == "bob"

    def test_invalid_args_calls_msg_with_help(self):
        c = ConcreteCommand()
        caller = MagicMock()
        # target is required; omit it
        run_fn, c_arg, parsed = c.execute(caller, "", cmdstring="test")
        # Should have sent help text to caller
        caller.msg.assert_called_once()
        help_text = caller.msg.call_args[0][0]
        assert "aliases:" in help_text
        # And returned None tuple
        assert run_fn is None
        assert c_arg is None
        assert parsed is None

    def test_cmdstring_default_empty(self):
        c = ConcreteCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "alice")
        # No cmdstring passed
        assert parsed.cmdstring == ""

    def test_shlex_strips_quotes(self):
        c = ConcreteCommand()
        caller = MagicMock()
        # 'alice "the builder"' — with posix=True, shlex strips the quotes
        # Result: ['alice', 'the builder']
        run_fn, _, parsed = c.execute(caller, 'alice "the builder"', cmdstring="test")
        # Two tokens -> target='alice' AND one extra positional 'the builder'
        # Argparse rejects the extra, so we get help text and (None, None, None)
        assert run_fn is None
        assert parsed is None
        caller.msg.assert_called_once()
        # Verify shlex behavior directly
        assert shlex.split('alice "the builder"', posix=True) == ['alice', 'the builder']

    def test_shlex_simple_split_with_required_target(self):
        c = ConcreteCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "alice", cmdstring="test")
        # One positional: parsed as target
        assert parsed.target == "alice"

    def test_shlex_with_no_args_optional(self):
        # Empty string: arg_list = []
        c = OptionalArgsCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "", cmdstring="x")
        # No required args, so parses fine
        assert run_fn is not None
        assert parsed.flag is False
        caller.msg.assert_not_called()

    def test_shlex_optional_with_one_arg(self):
        c = OptionalArgsCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "--name bob", cmdstring="x")
        assert parsed.name == "bob"

    def test_args_with_spaces_split(self):
        # Verify shlex.split behavior on simple input
        c = OptionalArgsCommand()
        caller = MagicMock()
        run_fn, _, parsed = c.execute(caller, "--name hello world", cmdstring="x")
        # Two tokens: '--name' and 'hello'; 'world' is extra -> argparse error
        assert run_fn is None
        assert parsed is None
        caller.msg.assert_called_once()

    def test_execute_returns_tuple_of_callable_caller_args(self):
        c = ConcreteCommand()
        caller = MagicMock()
        result = c.execute(caller, "alice", cmdstring="test")
        assert isinstance(result, tuple)
        assert len(result) == 3
        run_fn, c_arg, parsed = result
        assert callable(run_fn)
        assert c_arg is caller
        # parsed is a Namespace
        assert hasattr(parsed, "target")


class TestSetState:
    def test_setstate_creates_parser(self):
        c = ConcreteCommand()
        # Force parser creation
        _ = c.parser
        assert c._parser is not None
        # Now simulate unpickling: pickle.dumps and loads
        c2 = pickle.loads(pickle.dumps(c))
        assert c2._parser is not None
        assert isinstance(c2.parser, GameArgumentParser)
        # Args were preserved
        actions = {a.dest for a in c2.parser._actions}
        assert "target" in actions
        assert "flag" in actions

    def test_setstate_copies_state(self):
        c = ConcreteCommand()
        c.tag = "custom-tag"
        c2 = pickle.loads(pickle.dumps(c))
        assert c2.tag == "custom-tag"
        assert c2.key == "test"
        assert c2.aliases == ["t", "tst"]

    def test_deepcopy_works(self):
        c = ConcreteCommand()
        c2 = copy.deepcopy(c)
        assert c2.key == "test"
        # Parser should be rebuilt
        assert c2._parser is not None
        assert isinstance(c2.parser, GameArgumentParser)

    def test_setstate_use_parser_false(self):
        c = NoParserCommand()
        c2 = pickle.loads(pickle.dumps(c))
        # NoParserCommand has use_parser=False, so no parser after setstate
        assert c2._parser is None
        # Confirm by accessing .parser which returns None
        assert c2.parser is None


class TestCommandIntegration:
    def test_full_run_flow(self):
        c = OptionalArgsCommand()
        received = {}

        def my_run(caller, args):
            received["caller"] = caller
            received["args"] = args
            return "ran"

        c.run = my_run

        caller = MagicMock()
        run_fn, c_arg, parsed = c.execute(caller, "--name bob", cmdstring="opt")
        result = run_fn(caller, parsed)
        assert result == "ran"
        assert received["caller"] is caller
        assert received["args"] is parsed
        assert received["args"].name == "bob"
        assert received["args"].flag is False

    def test_help_message_format(self):
        c = ConcreteCommand()
        caller = MagicMock()
        c.execute(caller, "", cmdstring="test")
        # The help message sent to caller
        msg = caller.msg.call_args[0][0]
        # Should contain key, description, aliases, extra_desc
        assert "test" in msg
        assert "A test command" in msg
        assert "aliases:" in msg
        assert "extra info" in msg


# ---------------------------------------------------------------------------
# Object.execute_cmd — folded from test_execute_cmd.py (182 lines, 8 tests)
# per test_plan.md §2.3: execute_cmd tests belong with Command dispatch.
# ---------------------------------------------------------------------------

def _wait_for(predicate, timeout: float = 5.0) -> bool:
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
