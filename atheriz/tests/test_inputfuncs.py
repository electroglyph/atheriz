"""Tests for atheriz.inputfuncs — InputFuncs handler dispatcher and @inputfunc decorator."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atheriz.inputfuncs import InputFuncs, inputfunc
import atheriz.settings as settings


class TestInputfuncDecorator:
    def test_default_name_uses_function_name(self):
        @inputfunc()
        def my_handler(*args, **kwargs):
            pass
        assert my_handler._inputfunc_name == "my_handler"

    def test_explicit_name(self):
        @inputfunc("custom")
        def foo(*args, **kwargs):
            pass
        assert foo._inputfunc_name == "custom"

    def test_decorator_preserves_function(self):
        @inputfunc()
        def my_handler(*args, **kwargs):
            return 42
        assert my_handler() == 42


class TestGetHandlers:
    def test_finds_decorated_methods(self, global_test_env):
        class MyInput(InputFuncs):
            @inputfunc()
            def foo(self, c, a, k):
                pass

            @inputfunc("bar")
            def bar_method(self, c, a, k):
                pass

        inp = MyInput()
        handlers = inp.get_handlers()
        assert "foo" in handlers
        assert "bar" in handlers

    def test_ignores_undecorated_methods(self, global_test_env):
        class MyInput(InputFuncs):
            @inputfunc()
            def foo(self, c, a, k):
                pass

            def not_a_handler(self):
                pass

        inp = MyInput()
        handlers = inp.get_handlers()
        assert "foo" in handlers
        assert "not_a_handler" not in handlers

    def test_ignores_inherited_methods(self, global_test_env):
        # Only the methods decorated in THIS class are returned
        inp = InputFuncs()
        handlers = inp.get_handlers()
        # The base class has text, term_size, map_size, screenreader, client_ready
        assert "text" in handlers
        assert "term_size" in handlers
        assert "map_size" in handlers
        assert "screenreader" in handlers
        assert "client_ready" in handlers


class TestTermSize:
    def test_sets_session_dims(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 0
        conn.session.term_height = 0
        inp.term_size(conn, [100, 50], {})
        assert conn.session.term_width == 100
        assert conn.session.term_height == 50

    def test_short_args_ignored(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 80
        inp.term_size(conn, [100], {})  # only 1 arg
        # Width not updated
        assert conn.session.term_width == 80

    def test_rejects_non_int_types(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 80
        conn.session.term_height = 45
        inp.term_size(conn, ["hello", [1, 2, 3]], {})
        assert conn.session.term_width == 80
        assert conn.session.term_height == 45

    def test_rejects_zero(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 80
        conn.session.term_height = 45
        inp.term_size(conn, [0, 0], {})
        assert conn.session.term_width == 80
        assert conn.session.term_height == 45

    def test_rejects_negative(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 80
        conn.session.term_height = 45
        inp.term_size(conn, [-1, 80], {})
        assert conn.session.term_width == 80
        assert conn.session.term_height == 45

    def test_rejects_over_max(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 80
        conn.session.term_height = 45
        inp.term_size(conn, [settings.TERM_SIZE_MAX_WIDTH + 1, 50], {})
        assert conn.session.term_width == 80
        assert conn.session.term_height == 45

    def test_accepts_valid(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.term_width = 0
        conn.session.term_height = 0
        inp.term_size(conn, [24, 80], {})
        assert conn.session.term_width == 24
        assert conn.session.term_height == 80
    def test_sets_session_dims(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 0
        conn.session.map_height = 0
        inp.map_size(conn, [30, 20], {})
        assert conn.session.map_width == 30
        assert conn.session.map_height == 20

    def test_short_args_ignored(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 5
        inp.map_size(conn, [], {})
        # Width not updated
        assert conn.session.map_width == 5

    def test_rejects_non_int_types(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 5
        conn.session.map_height = 5
        inp.map_size(conn, ["bad", None], {})
        assert conn.session.map_width == 5
        assert conn.session.map_height == 5

    def test_rejects_zero(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 5
        conn.session.map_height = 5
        inp.map_size(conn, [0, 0], {})
        assert conn.session.map_width == 5
        assert conn.session.map_height == 5

    def test_rejects_negative(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 5
        conn.session.map_height = 5
        inp.map_size(conn, [-1, 20], {})
        assert conn.session.map_width == 5
        assert conn.session.map_height == 5

    def test_rejects_over_max(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 5
        conn.session.map_height = 5
        inp.map_size(conn, [50, settings.MAP_SIZE_MAX_HEIGHT + 1], {})
        assert conn.session.map_width == 5
        assert conn.session.map_height == 5

    def test_accepts_valid(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.map_width = 0
        conn.session.map_height = 0
        inp.map_size(conn, [30, 20], {})
        assert conn.session.map_width == 30
        assert conn.session.map_height == 20


class TestScreenreader:
    def test_enables(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.screenreader = False
        inp.screenreader(conn, [True], {})
        assert conn.session.screenreader is True

    def test_disables(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.screenreader = True
        inp.screenreader(conn, [False], {})
        assert conn.session.screenreader is False

    def test_no_args_noop(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.screenreader = False
        inp.screenreader(conn, [], {})
        # Stays False
        assert conn.session.screenreader is False

    def test_sends_confirmation(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        inp.screenreader(conn, [True], {})
        # A confirmation msg was sent
        conn.msg.assert_called()
        assert "enabled" in conn.msg.call_args.args[0].lower()


class TestTextRouting:
    def test_empty_text_noop(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.input_future = None
        # Empty text should return without doing anything
        inp.text(conn, [""], {})
        # No msg sent, no error
        conn.msg.assert_not_called()

    def test_no_args(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        conn.session.input_future = None
        inp.text(conn, [], {})  # no args
        # Should not raise


class TestResolveInputFuture:
    def test_sets_future_result_when_waiting(self, global_test_env):
        # INTENT: when a future is set on the session, the text is delivered to it
        import asyncio
        inp = InputFuncs()
        conn = MagicMock()
        captured = {}

        async def run():
            future = asyncio.Future()
            conn.session.input_future = future
            # Set puppet to None so we go through the unloggedin path
            conn.session.puppet = None
            inp.text(conn, ["my input"], {})
            try:
                result = await asyncio.wait_for(future, timeout=1.0)
                captured["result"] = result
                captured["future_cleared"] = conn.session.input_future is None
            except asyncio.TimeoutError:
                captured["timeout"] = True

        asyncio.new_event_loop().run_until_complete(run())
        assert captured.get("result") == "my input"
        assert captured.get("future_cleared") is True

    def test_does_not_process_command_when_future_set(self, global_test_env):
        # INTENT: when a future is pending, text goes to the future not a command
        import asyncio
        inp = InputFuncs()
        conn = MagicMock()
        captured = {}

        async def run():
            future = asyncio.Future()
            conn.session.input_future = future
            conn.session.puppet = None
            inp.text(conn, ["hello"], {})
            try:
                result = await asyncio.wait_for(future, timeout=1.0)
                captured["result"] = result
                captured["future_cleared"] = conn.session.input_future is None
            except asyncio.TimeoutError:
                captured["timeout"] = True

        asyncio.new_event_loop().run_until_complete(run())
        # Future got the text and was cleared
        assert captured.get("result") == "hello"
        assert captured.get("future_cleared") is True


class TestClientReady:
    def test_sends_welcome(self, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        inp.client_ready(conn, [], {})
        # welcome screen was sent
        assert conn.msg.call_count >= 1
        # And a prompt
        all_msgs = [c for c in conn.msg.call_args_list]
        # Find the prompt call
        prompt_call = [c for c in all_msgs if "prompt" in c.kwargs]
        assert len(prompt_call) >= 1

    @patch("importlib.reload")
    def test_connection_screen_not_reloaded_on_connect(self, mock_reload, global_test_env):
        inp = InputFuncs()
        conn = MagicMock()
        inp.client_ready(conn, [], {})
        inp.client_ready(conn, [], {})
        mock_reload.assert_not_called()


class TestSubclassing:
    def test_subclass_can_add_handlers(self, global_test_env):
        class MyInput(InputFuncs):
            @inputfunc("my_custom")
            def my_handler(self, c, a, k):
                pass

        inp = MyInput()
        handlers = inp.get_handlers()
        assert "my_custom" in handlers
        # Parent handlers still present
        assert "text" in handlers


class TestCustomVerbNotShadowedByGluedAlias:
    def test_custom_verb_l_not_shadowed_by_look(self, global_test_env):
        from atheriz.inputfuncs import dispatch_loggedin
        from atheriz.commands.base_cmd import Command
        from atheriz.objects.base_obj import Object
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord
        from atheriz.globals.objects import add_object
        from unittest.mock import MagicMock, patch

        room = Node(coord=Coord("test", 20, 20, 0))
        add_object(room)
        puppet = Object.create(None, "Tester", is_pc=True)
        puppet.location = room
        room.add_object(puppet)
        puppet.msg = MagicMock()

        class LCustomCommand(Command):
            key = "lcustom"
            def run(self, caller, args):
                caller.msg("custom lcustom executed")

        prop = Object.create(None, "mystery-box")
        prop.external_cmdset.add(LCustomCommand())
        prop.move_to(room)

        with patch("atheriz.inputfuncs.get_async_threadpool") as mock_pool:
            mock_run = MagicMock()
            mock_pool.return_value.run = mock_run
            mock_pool.return_value.add_task = MagicMock(return_value=True)
            job = dispatch_loggedin(puppet, "lcustom", immediate=True)
            assert job is not None, "dispatch should return job for external lcustom"
            func, caller, eargs = job
            assert "lcustom" in str(func.__self__.key).lower() or func.__self__.key == "lcustom", f"glued alias shadowed external: got {func.__self__.key}"

    def test_external_l_single_char_not_shadowed_by_glued_look(self, global_test_env):
        from atheriz.inputfuncs import dispatch_loggedin
        from atheriz.commands.base_cmd import Command
        from atheriz.objects.base_obj import Object
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord
        from atheriz.globals.objects import add_object
        from unittest.mock import MagicMock, patch

        room = Node(coord=Coord("test", 21, 21, 0))
        add_object(room)
        puppet = Object.create(None, "Tester2", is_pc=True)
        puppet.location = room
        room.add_object(puppet)
        puppet.msg = MagicMock()

        class LCommand(Command):
            key = "l"
            def run(self, caller, args):
                caller.msg("external l executed")

        prop = Object.create(None, "box2")
        prop.external_cmdset.add(LCommand())
        prop.move_to(room)

        with patch("atheriz.inputfuncs.get_async_threadpool") as mock_pool:
            mock_pool.return_value.run = MagicMock()
            mock_pool.return_value.add_task = MagicMock(return_value=True)
            job = dispatch_loggedin(puppet, "l", immediate=True)
            assert job is not None
            func, caller2, eargs = job
            assert func.__self__.key == "l" and func.__self__.key != "look", f"expected external 'l', got {func.__self__.key}"


class TestHelpCaseInsensitive:
    def test_help_look_case_insensitive(self, global_test_env):
        from atheriz.commands.loggedin.help import HelpCommand
        from atheriz.objects.base_obj import Object
        from unittest.mock import MagicMock
        caller = Object.create(None, "Helper")
        caller.privilege_level = __import__("atheriz.settings", fromlist=["Privilege"]).Privilege.Player
        caller.quelled = False
        caller.msg = MagicMock()
        caller.location = None
        caller.session = MagicMock(screenreader=True, term_width=80)
        args = MagicMock(command="LOOK")
        HelpCommand().run(caller, args)
        all_text = " ".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        assert "not found" not in all_text.lower(), "help LOOK should find look case-insensitively"
        assert "look" in all_text.lower()

    def test_help_uppercase_external(self, global_test_env):
        from atheriz.commands.loggedin.help import HelpCommand
        from atheriz.commands.base_cmd import Command
        from atheriz.objects.base_obj import Object
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord
        from atheriz.globals.objects import add_object
        from unittest.mock import MagicMock
        room = Node(coord=Coord("test", 22, 22, 0))
        add_object(room)
        caller = Object.create(None, "Helper2")
        caller.privilege_level = __import__("atheriz.settings", fromlist=["Privilege"]).Privilege.Player
        caller.quelled = False
        caller.msg = MagicMock()
        caller.location = room
        room.add_object(caller)
        caller.session = MagicMock(screenreader=True, term_width=80)

        class MyExt(Command):
            key = "myverb"
            desc = "My external verb"
            def run(self, caller, args):
                pass

        prop = Object.create(None, "prop")
        prop.external_cmdset.add(MyExt())
        prop.move_to(room)
        args = MagicMock(command="MYVERB")
        HelpCommand().run(caller, args)
        all_text = " ".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        assert "not found" not in all_text.lower()
        assert "myverb" in all_text.lower()


class TestNoneCommandIncludesExternal:
    def test_none_suggests_external_verb(self, global_test_env):
        from atheriz.commands.loggedin.none import NoneCommand
        from atheriz.commands.base_cmd import Command
        from atheriz.objects.base_obj import Object
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord
        from atheriz.globals.objects import add_object
        from unittest.mock import MagicMock
        room = Node(coord=Coord("test", 23, 23, 0))
        add_object(room)
        caller = Object.create(None, "Typer")
        caller.location = room
        room.add_object(caller)
        caller.msg = MagicMock()
        caller.internal_cmdset = __import__("atheriz.commands.base_cmdset", fromlist=["CmdSet"]).CmdSet()
        prop = Object.create(None, "prop2")
        class ExtCmd(Command):
            key = "flurble"
            desc = "external flurble"
            def run(self, caller, args):
                pass
        prop.external_cmdset.add(ExtCmd())
        prop.move_to(room)
        args = MagicMock(none=["flurbe"])
        NoneCommand().run(caller, args)
        all_text = " ".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        assert "flurble" in all_text.lower(), "typo suggestion should include external verb flurble"
