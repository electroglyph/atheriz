"""Issue tests: Door.map_close/map_open dereference `self.to_coord.area`
without checking whether `to_coord` is None, crashing on doors without a
destination.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atheriz.objects.base_door import Door
from atheriz.utils import Coord


class TestDoorMap:
    def test_map_close_without_to_coord(self, global_test_env):
        """INTENT: closing a door that has no to_coord must not crash."""
        d = Door(
            from_coord=Coord("test", 0, 0, 0),
            from_exit="east",
            to_coord=None,
            to_exit=None,
            symbol_coord=(5, 5),
        )
        with patch("atheriz.settings.MAP_ENABLED", True):
            d.map_close()

    def test_map_open_without_to_coord(self, global_test_env):
        """INTENT: opening a door that has no to_coord must not crash."""
        d = Door(
            from_coord=Coord("test", 0, 0, 0),
            from_exit="east",
            to_coord=None,
            to_exit=None,
            symbol_coord=(5, 5),
        )
        with patch("atheriz.settings.MAP_ENABLED", True):
            d.map_open()
