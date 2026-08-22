"""Issue tests: hot reload permanently killed all object ticks.

do_reload() called get_async_ticker().clear(), emptying every slot — including
every tickable Object's and Node's at_tick registration. Only GameTime and
autosave (which manage their own lifecycles) ever ticked again; world
simulation silently stopped until reboot. Fix: after the clear, walk the object
registry and node handler and re-add every tickable. Re-registration is
idempotent because equal bound methods collapse in a TimeSlot's coro set.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

import atheriz.globals.startstop as ss
from atheriz.coord import Coord
from atheriz.globals.get import get_async_ticker, get_node_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeArea, NodeGrid


def _do_reload_with_externals_mocked():
    with patch.object(ss, "get_server_channel", return_value=None), \
         patch.object(ss, "save_objects"), \
         patch.object(ss, "start_autosave"), \
         patch.object(ss, "stop_autosave"), \
         patch("atheriz.server_events"), \
         patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
         patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False):
        ss.do_reload()


def _wait(cond, timeout=3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


class TestTicksSurviveReload:
    def test_tickable_object_ticks_after_reload(self, global_test_env):
        """INTENT: an object registered with the ticker before do_reload must
        still be ticking afterwards — clear() must not strand it."""
        calls = []
        obj = Object.create(None, "Ticker")
        obj.at_tick = MagicMock(side_effect=lambda *a, **k: calls.append(1))
        obj.is_tickable = True
        obj.tick_seconds = 0.05

        assert _wait(lambda: len(calls) >= 1), "object never ticked pre-reload"

        _do_reload_with_externals_mocked()

        count_before = len(calls)
        assert _wait(lambda: len(calls) > count_before), "object stopped ticking after reload"

    def test_non_tickable_object_not_registered(self, global_test_env):
        """INTENT: re-registration only touches _is_tickable objects; a plain
        object gains no ticker entry."""
        obj = Object.create(None, "Plain")
        obj.at_tick = MagicMock()

        _do_reload_with_externals_mocked()

        for slot in get_async_ticker().slots.values():
            assert obj.at_tick not in slot.coros


class TestNodeReRegistration:
    def test_tickable_node_reregistered(self, global_test_env):
        """INTENT: tickable nodes discovered through the handler's
        nh.lock -> area.lock -> grid.lock traversal are re-added after reload."""
        nh = get_node_handler()
        area = NodeArea(name="tick-area")
        grid = NodeGrid(area="tick-area", z=0)
        node = Node(coord=Coord("tick-area", 0, 0, 0))
        node.at_tick = MagicMock()
        node._is_tickable = True
        grid.nodes[(0, 0)] = node
        area.grids[0] = grid
        with nh.lock:
            nh.areas["tick-area"] = area

        try:
            ss._reregister_ticks()

            bound = node.at_tick
            assert any(bound in s.coros for s in get_async_ticker().slots.values())
        finally:
            with nh.lock:
                nh.areas.pop("tick-area", None)


class TestRobustness:
    def test_broken_at_tick_does_not_abort_rest(self, global_test_env):
        """INTENT: one object whose registration raises must not prevent other
        objects from being re-registered."""
        bad = Object.create(None, "BadTick")
        bad.at_tick = MagicMock()
        bad.is_tickable = True
        good_calls = []
        good = Object.create(None, "GoodTick")
        good.at_tick = MagicMock(side_effect=lambda *a, **k: good_calls.append(1))
        good.is_tickable = True
        good.tick_seconds = 0.05

        real_ticker = get_async_ticker()

        def fake_add(coro, seconds):
            if getattr(coro, "__self__", None) is bad:
                raise RuntimeError("boom")
            return real_ticker.add_coro(coro, seconds)

        mock_ticker = MagicMock()
        mock_ticker.add_coro.side_effect = fake_add

        with patch.object(ss, "get_async_ticker", return_value=mock_ticker):
            ss._reregister_ticks()

        assert any(good.at_tick in s.coros for s in real_ticker.slots.values())
        assert _wait(lambda: len(good_calls) >= 1)

    def test_mocked_node_handler_does_not_crash(self, global_test_env):
        """INTENT: existing do_reload tests patch get_node_handler with bare
        MagicMocks; the helper must tolerate non-iterable shapes by logging and
        continuing."""
        with patch.object(ss, "get_node_handler", return_value=MagicMock()):
            ss._reregister_ticks()


class TestEngineCorosOnce:
    def test_engine_coro_registered_exactly_once(self, global_test_env):
        """INTENT: engine coros restarted by their own managers (autosave here,
        simulated via start_autosave spy) are not duplicated by re-registration,
        which only walks objects/nodes."""
        added = []
        real_ticker = get_async_ticker()

        class SpyTicker:
            def __getattr__(self, name):
                return getattr(real_ticker, name)

            def add_coro(self, coro, seconds):
                added.append((coro, seconds))
                return real_ticker.add_coro(coro, seconds)

        def fake_start_autosave():
            SpyTicker().add_coro(_engine_marker, 60)

        obj = Object.create(None, "Ticker2")
        obj.at_tick = MagicMock()
        obj.is_tickable = True
        obj.tick_seconds = 30.0

        with patch.object(ss, "get_server_channel", return_value=None), \
             patch.object(ss, "save_objects"), \
             patch.object(ss, "stop_autosave"), \
             patch("atheriz.server_events"), \
             patch.object(ss.settings, "TIME_SYSTEM_ENABLED", False), \
             patch.object(ss.settings, "AUTOSAVE_ON_RELOAD", False), \
             patch.object(ss, "start_autosave", side_effect=fake_start_autosave):
            ss.do_reload()

        assert added.count((_engine_marker, 60)) == 1


def _engine_marker():
    pass
