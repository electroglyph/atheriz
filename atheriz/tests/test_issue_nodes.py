"""Issue tests: Node/NodeGrid/NodeArea defensive behaviors — empty-grid random
selection, missing-key removal, string formatting, and hashability.
"""
from __future__ import annotations

import pytest

from atheriz.globals.node import NodeHandler
from atheriz.globals.objects import add_object
from atheriz.objects.nodes import Node, NodeArea, NodeGrid
from atheriz.utils import Coord


class TestNodeGrid:
    def test_get_random_node_on_empty_grid_returns_none(self, global_test_env):
        """INTENT: selecting a random node from an empty grid must return None,
        not raise IndexError from random.choice([])."""
        grid = NodeGrid(area="test", z=0)
        assert grid.get_random_node() is None

    def test_get_random_node_returns_existing_node(self, global_test_env):
        grid = NodeGrid(area="test", z=0)
        node = Node(coord=Coord("test", 3, 3, 0))
        grid.add_node(node)
        assert grid.get_random_node() == node


class TestNodeArea:
    def test_remove_data_missing_key_is_noop(self, global_test_env):
        """INTENT: removing data for a missing key must not raise KeyError."""
        area = NodeArea(name="testarea")
        area.remove_data("missing")

    def test_str_includes_area_name(self, global_test_env):
        """INTENT: str(area) must include the area name; today the label is used
        as a join separator and vanishes for a single-grid area."""
        area = NodeArea(name="testarea")
        grid = NodeGrid(area="testarea", z=0)
        grid.add_node(Node(coord=Coord("testarea", 0, 0, 0)))
        area.add_grid(grid)
        assert "testarea" in str(area)


class TestNodeHashability:
    def test_node_is_hashable(self, global_test_env):
        """INTENT: Node defines __eq__ without __hash__, which makes it
        unhashable (TypeError). It must remain hashable so it can live in sets
        (e.g. the ticker's coro set)."""
        n = Node(coord=Coord("test", 0, 0, 0))
        add_object(n)
        s = {n}
        assert n in s


class TestNodeHandler:
    def test_remove_area_missing_is_noop(self, global_test_env):
        """INTENT: removing a non-existent area must not raise KeyError."""
        handler = NodeHandler()
        handler.remove_area("missing")

    def test_remove_transition_missing_is_noop(self, global_test_env):
        """INTENT: removing a non-existent transition must not raise KeyError."""
        handler = NodeHandler()
        handler.remove_transition(Coord("missing", 0, 0, 0))
