"""Issue tests: `build`'s has_args check omits the `-x` and `--round` flags, so
`build -x` and `build -x --round` silently print help instead of building.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atheriz.commands.loggedin.build import BuildCommand
from atheriz.globals.node import NodeHandler
from atheriz.objects.nodes import Node, NodeArea, NodeGrid
from atheriz.utils import Coord


class MockMapHandler:
    def __init__(self):
        self.data = {}

    def get_mapinfo(self, area, z):
        return self.data.get((area, z))

    def _get_or_create(self, area, z):
        from atheriz.globals.map import MapInfo

        mi = self.data.get((area, z))
        if mi is None:
            mi = MapInfo(name=area)
            self.data[(area, z)] = mi
        return mi

    def set_mapinfo(self, area, z, mi):
        self.data[(area, z)] = mi


class MockCaller:
    def __init__(self, location=None):
        self.location = location
        self.is_builder = True
        self.messages = []
        self._moved_to = []

    def msg(self, text=None, **kwargs):
        self.messages.append(text)

    def move_to(self, destination, **kwargs):
        self.location = destination
        self._moved_to.append(destination)


def make_args(**kwargs):
    defaults = {
        "n": False, "e": False, "s": False, "w": False, "u": False, "d": False,
        "x": False, "room": False, "road": False, "path": False, "desc": None,
        "single": False, "double": False, "round": False, "none": False,
    }
    defaults.update(kwargs)

    class Args:
        pass

    a = Args()
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


def _setup():
    nh = NodeHandler()
    mh = MockMapHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(area="TestArea", z=0)
    start_node = Node(coord=Coord("TestArea", 0, 0, 0))
    grid.nodes[(0, 0)] = start_node
    area.add_grid(grid)
    nh.add_area(area)
    caller = MockCaller(location=start_node)
    return nh, mh, start_node, caller


class TestBuildHereFlag:
    def test_build_x_alone_builds_here(self, global_test_env):
        """INTENT: `build -x` must build at the current location instead of
        showing help."""
        nh, mh, start_node, caller = _setup()
        cmd = BuildCommand()
        with patch(
            "atheriz.commands.loggedin.build.get_node_handler", return_value=nh
        ), patch("atheriz.commands.loggedin.build.get_map_handler", return_value=mh):
            cmd.run(caller, make_args(x=True))

        assert caller._moved_to, "caller should have been moved to the node built here"
        assert caller._moved_to[0] == start_node

    def test_build_x_with_round_builds_here(self, global_test_env):
        """INTENT: `build -x --round` must be recognized (both flags were left
        out of has_args) and build at the current location."""
        nh, mh, start_node, caller = _setup()
        cmd = BuildCommand()
        with patch(
            "atheriz.commands.loggedin.build.get_node_handler", return_value=nh
        ), patch("atheriz.commands.loggedin.build.get_map_handler", return_value=mh):
            cmd.run(caller, make_args(x=True, round=True))

        assert caller._moved_to, "caller should have been moved to the node built here"
        assert caller._moved_to[0] == start_node
