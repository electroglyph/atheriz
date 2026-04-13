import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from atheriz.menu import Choice, MenuContext, MenuEngine, run_menu


def node_start(ctx: MenuContext):
    return "Welcome! Choose an option.", [
        Choice(key="1", desc="Go to confirm", goto=node_confirm),
        Choice(key="2", desc="Stay here", goto=node_start),
        Choice(key="Q", desc="Quit", goto=None),
    ]


def node_confirm(ctx: MenuContext):
    ctx.state["confirmed"] = True
    return "Are you sure?", [
        Choice(key="Y", desc="Yes", goto=node_finish),
        Choice(key="N", desc="No", goto=node_start),
    ]


def node_finish(ctx: MenuContext):
    return "Done!", [
        Choice(key="X", desc="Exit", goto=None),
    ]


def node_with_callback(ctx: MenuContext):
    def on_select(c):
        c.state["selected"] = True

    return "Pick one", [
        Choice(key="1", desc="Select", goto=None, callback=on_select),
    ]


def node_with_stay(ctx: MenuContext):
    def on_select(c):
        c.state["toggled"] = True

    return "Toggle", [
        Choice(key="1", desc="Toggle", callback=on_select, stay=True),
    ]


def node_empty(ctx: MenuContext):
    return "Dead end", []


# ==================== Dataclass Tests ====================


def test_menucontext_defaults():
    ctx = MenuContext(caller="player")
    assert ctx.caller == "player"
    assert ctx.state == {}


def test_menucontext_with_state():
    ctx = MenuContext(caller="player", state={"key": "val"})
    assert ctx.state == {"key": "val"}


def test_choice_defaults():
    c = Choice(key="1", desc="Option")
    assert c.key == "1"
    assert c.desc == "Option"
    assert c.goto is None
    assert c.callback is None


def test_choice_with_goto_and_callback():
    cb = lambda ctx: None
    c = Choice(key="Y", desc="Yes", goto=node_start, callback=cb)
    assert c.goto is node_start
    assert c.callback is cb


# ==================== MenuEngine Tests ====================


def test_engine_init():
    engine = MenuEngine("player", node_start)
    assert engine.current_node is node_start
    assert "Welcome!" in engine._current_text
    assert len(engine._current_choices) == 3


def test_engine_get_display():
    engine = MenuEngine("player", node_start)
    display = engine.get_display()
    assert "Welcome!" in display
    assert "[1]" in display
    assert "[Q]" in display
    assert "Go to confirm" in display


def test_engine_get_display_empty_when_closed():
    engine = MenuEngine("player", node_start)
    engine.current_node = None
    assert engine.get_display() == ""


def test_engine_handle_input_transitions():
    engine = MenuEngine("player", node_start)
    result = engine.handle_input("1")
    assert result is True
    assert engine.current_node is node_confirm


def test_engine_handle_input_exits():
    engine = MenuEngine("player", node_start)
    result = engine.handle_input("q")
    assert result is False
    assert engine.current_node is None


def test_engine_handle_input_invalid_stays():
    engine = MenuEngine("player", node_start)
    result = engine.handle_input("z")
    assert result is True
    assert engine.current_node is node_start


def test_engine_handle_input_case_insensitive():
    engine = MenuEngine("player", node_start)
    assert engine.handle_input("Q") is False
    assert engine.current_node is None


def test_engine_handle_input_strips_whitespace():
    engine = MenuEngine("player", node_start)
    assert engine.handle_input("  q  ") is False
    assert engine.current_node is None


def test_engine_callback_executed():
    engine = MenuEngine("player", node_with_callback)
    assert engine.context.state.get("selected") is None
    engine.handle_input("1")
    assert engine.context.state.get("selected") is True


def test_engine_stay_executes_callback_and_stays():
    engine = MenuEngine("player", node_with_stay)
    assert engine.context.state.get("toggled") is None
    result = engine.handle_input("1")
    assert result is True
    assert engine.current_node is node_with_stay
    assert engine.context.state.get("toggled") is True


def test_engine_empty_choices_exits():
    engine = MenuEngine("player", node_empty)
    result = engine.handle_input("anything")
    assert result is False
    assert engine.current_node is None


def test_engine_backward_navigation():
    engine = MenuEngine("player", node_start)
    engine.handle_input("1")
    assert engine.current_node is node_confirm
    engine.handle_input("n")
    assert engine.current_node is node_start


def test_engine_display_updates_after_transition():
    engine = MenuEngine("player", node_start)
    assert "Welcome!" in engine.get_display()
    engine.handle_input("1")
    assert "Are you sure?" in engine.get_display()


def test_engine_state_persists_across_nodes():
    engine = MenuEngine("player", node_start)
    engine.handle_input("1")
    assert engine.context.state.get("confirmed") is True
    engine.handle_input("n")
    assert engine.context.state.get("confirmed") is True


def test_engine_close():
    engine = MenuEngine("player", node_start)
    engine.handle_input("1")
    assert engine.context.state.get("confirmed") is True
    engine.close()
    assert engine.current_node is None
    assert engine._current_text == ""
    assert engine._current_choices == {}
    assert engine.context.state == {}


# ==================== run_menu Tests ====================


def _make_loop():
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, t


def _stop_loop(loop, t):
    loop.call_soon_threadsafe(loop.stop)
    t.join(timeout=2)


def test_run_menu_full_flow():
    responses = iter(["1", "N", "Q"])

    class FakeSession:
        async def prompt(self, text):
            return next(responses)

    class FakeCaller:
        def __init__(self):
            self.session = FakeSession()

    caller = FakeCaller()
    loop, t = _make_loop()

    mock_atp = MagicMock()
    mock_atp.loop = loop

    with patch("atheriz.globals.get.get_async_threadpool", return_value=mock_atp):
        run_menu(caller, node_start)

    _stop_loop(loop, t)


def test_run_menu_exit_immediately():
    class FakeSession:
        async def prompt(self, text):
            return "Q"

    class FakeCaller:
        def __init__(self):
            self.session = FakeSession()

    caller = FakeCaller()
    loop, t = _make_loop()

    mock_atp = MagicMock()
    mock_atp.loop = loop

    with patch("atheriz.globals.get.get_async_threadpool", return_value=mock_atp):
        run_menu(caller, node_start)

    _stop_loop(loop, t)


def test_run_menu_multi_step():
    responses = iter(["1", "Y", "X"])

    class FakeSession:
        async def prompt(self, text):
            return next(responses)

    class FakeCaller:
        def __init__(self):
            self.session = FakeSession()
            self.finished = False

    caller = FakeCaller()
    loop, t = _make_loop()

    mock_atp = MagicMock()
    mock_atp.loop = loop

    with patch("atheriz.globals.get.get_async_threadpool", return_value=mock_atp):
        run_menu(caller, node_start)

    _stop_loop(loop, t)
