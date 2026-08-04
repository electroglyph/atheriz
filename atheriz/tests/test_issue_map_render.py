"""Issue tests: MapInfo.render/render_legend crash when a mapable object has
no location (`o.location.coord` on None).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz.globals.map import MapInfo
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.utils import Coord


def _make_listener():
    listener = Object.create(None, "listener")
    listener.map_enabled = True
    listener.last_map_time = None
    listener.at_pre_map_render = MagicMock(side_effect=lambda g: g)
    listener.at_map_update = MagicMock()
    listener.at_legend_update = MagicMock()
    return listener


class TestMapRender:
    def test_render_skips_object_without_location(self, global_test_env):
        """INTENT: rendering the map must skip mapables whose location is None
        (e.g. a mid-teleport or unplaced object) instead of crashing."""
        mi = MapInfo(name="test")
        mi.pre_grid[(0, 0)] = "#"
        mi.map_changed = True

        listener = _make_listener()
        mi.add_listener(listener)

        stray = Object.create(None, "stray", is_mapable=True)
        stray.symbol = "S"
        stray.location = None
        mi.objects[stray.id] = stray

        mi.render(force=True)

        listener.at_map_update.assert_called_once()

    def test_render_legend_skips_object_without_location(self, global_test_env):
        """INTENT: rendering the legend must skip mapables whose location is
        None instead of crashing."""
        mi = MapInfo(name="test")

        listener = _make_listener()
        mi.add_listener(listener)

        stray = Object.create(None, "stray", is_mapable=True)
        stray.symbol = "S"
        stray.location = None
        mi.objects[stray.id] = stray

        mi.render_legend()

        listener.at_legend_update.assert_called_once()
