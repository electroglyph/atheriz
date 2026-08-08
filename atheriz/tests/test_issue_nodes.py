"""Issue tests: Node/NodeGrid/NodeArea defensive behaviors — empty-grid random
selection, missing-key removal, string formatting, hashability, delete
relocation, and overwrite warnings.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atheriz.globals.node import NodeHandler
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeArea, NodeGrid, NodeLink
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


class TestNodeDeleteRelocation:
    def test_nonrecursive_delete_does_not_orphan_contents(self, global_test_env):
        """INTENT: Node.delete(recursive=False) must relocate contents to a real
        location. Today it moves them to `content.home` (None for most objects),
        orphaning them off the map."""
        nh = NodeHandler()
        node = Node(coord=Coord("test", 5, 5, 0))
        fallback = Node(coord=Coord("test", 5, 4, 0))
        caller = Object.create(None, "caller")
        caller.move_to(fallback)
        obj = Object.create(None, "item")
        obj.move_to(node)
        assert obj.location is node

        with patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            node.delete(caller, recursive=False)

        assert obj.location is not None, "contents were orphaned off the map"
        assert obj.location is not node, "contents should have been relocated"

    def test_nonrecursive_delete_uses_home(self, global_test_env):
        """INTENT: when a content object does have a home, relocation must go
        there rather than to the caller's location."""
        nh = NodeHandler()
        node = Node(coord=Coord("test", 5, 5, 0))
        home_node = Node(coord=Coord("test", 0, 0, 0))
        caller = Object.create(None, "caller")
        obj = Object.create(None, "item")
        obj.home = home_node
        obj.move_to(node)

        with patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            node.delete(caller, recursive=False)

        assert obj.location is home_node


class TestNodeGridOverwrite:
    def test_add_node_overwrite_warns(self, global_test_env, capture_atheriz_log):
        """INTENT: overwriting an existing node at the same coordinates must log
        a warning. Today NodeGrid.add_node silently replaces it."""
        grid = NodeGrid(area="test", z=0)
        node_a = Node(coord=Coord("test", 0, 0, 0))
        node_a.add_link(NodeLink("north", Coord("test", 0, 2, 0), ["n"]))
        grid.add_node(node_a)

        node_b = Node(coord=Coord("test", 0, 0, 0))
        node_b.add_link(NodeLink("south", Coord("test", 0, -2, 0), ["s"]))
        grid.add_node(node_b)

        log = capture_atheriz_log()
        assert "overwrit" in log.lower(), f"no overwrite warning logged: {log!r}"
