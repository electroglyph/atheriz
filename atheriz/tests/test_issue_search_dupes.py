"""Issue tests: pluralized `search` queries return duplicate matches because an
object matching both a required and an optional term is appended twice.
"""
from __future__ import annotations

import pytest

from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


class TestSearchDuplicates:
    def test_plural_search_returns_each_object_once(self, global_test_env):
        """INTENT: `search("crates")` on a room with two crates must return each
        crate exactly once. The current implementation matches each crate via
        the required term ("crate") AND the optional terms ("crat"/"crate"),
        appending the same object twice."""
        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)

        crate1 = Object.create(None, "crate", is_item=True)
        crate2 = Object.create(None, "crate", is_item=True)
        node.add_object(crate1)
        node.add_object(crate2)

        results = node.search("crates")

        ids = [o.id for o in results]
        assert len(ids) == len(set(ids)), f"duplicate matches: {ids}"
        assert len(results) == 2

    def test_singular_search_returns_each_object_once(self, global_test_env):
        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)
        crate1 = Object.create(None, "crate", is_item=True)
        node.add_object(crate1)
        results = node.search("crate")
        assert results == [crate1]
