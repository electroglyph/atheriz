"""Tests for atheriz search — global registry and contents search.

Merged from test_search.py (global registry filter_by / get), test_search2.py
(contents search via atheriz.objects.contents.search), and test_search_dupes.py
(plural dedup regression). File-local ``clear_registry`` autouse fixtures
duplicated ``global_test_env`` (conftest.py:35) and have been removed; isolation
is now via ``global_test_env`` autouse (clears ``_ALL_OBJECTS`` etc.). Tests
declare ``global_test_env`` explicitly where registry isolation matters.
"""

from __future__ import annotations

import sys

import pytest

from atheriz.globals import objects
from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.contents import search
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


class MockObj:
    def __init__(self, id):
        self.id = id


class TestGlobalRegistrySearch:
    def test_search_bad(self, global_test_env):
        """Test searching with no parameters returns empty list."""
        assert objects.get(-1) == []
        assert objects.get([-1]) == []

    def test_search_by_id(self, global_test_env):
        """Test searching by ID only."""
        obj = MockObj(1)
        objects.add_object(obj)

        results = objects.get(1)
        assert len(results) == 1
        assert results[0] == obj

        results = objects.get(999)
        assert results == []

    def test_search_ids(self, global_test_env):
        """Test searching by list of IDs."""
        obj1 = MockObj(10)
        obj2 = MockObj(11)
        obj3 = MockObj(12)
        objects.add_object(obj1)
        objects.add_object(obj2)
        objects.add_object(obj3)

        results = objects.get([10, 12])
        assert len(results) == 2
        assert obj1 in results
        assert obj3 in results
        assert obj2 not in results

    def test_filter_by(self, global_test_env):
        """Test filtering objects by lambda."""
        obj1 = MockObj(20)
        obj1.is_active = True
        obj2 = MockObj(21)
        obj2.is_active = False
        obj3 = MockObj(22)
        obj3.is_active = True

        objects.add_object(obj1)
        objects.add_object(obj2)
        objects.add_object(obj3)

        results = objects.filter_by(lambda x: getattr(x, "is_active", False))
        assert len(results) == 2
        assert obj1 in results
        assert obj3 in results
        assert obj2 not in results


def _build_nested():
    """bag -> {coin, pouch(is_container) -> {sword}, box(not container) -> {gem}}."""
    bag = Object()
    bag.id = 1
    bag.name = "bag"
    add_object(bag)

    coin = Object()
    coin.id = 2
    coin.name = "coin"
    add_object(coin)
    bag.add_object(coin)

    pouch = Object()
    pouch.id = 3
    pouch.name = "pouch"
    pouch.is_container = True
    add_object(pouch)
    bag.add_object(pouch)

    sword = Object()
    sword.id = 4
    sword.name = "sword"
    add_object(sword)
    pouch.add_object(sword)

    box = Object()
    box.id = 5
    box.name = "box"
    add_object(box)
    bag.add_object(box)

    gem = Object()
    gem.id = 6
    gem.name = "gem"
    add_object(gem)
    box.add_object(gem)

    return bag, coin, pouch, sword, box, gem


def _build_chain(depth: int):
    """Build a linear chain of `depth` containers: bag -> c1 -> c2 -> ... -> deepest."""
    bag = Object()
    bag.id = 1
    bag.name = "bag"
    add_object(bag)

    parent = bag
    next_id = 2
    for _ in range(depth):
        c = Object()
        c.id = next_id
        c.name = f"c{next_id}"
        c.is_container = True
        add_object(c)
        parent.add_object(c)
        parent = c
        next_id += 1

    deepest = Object()
    deepest.id = next_id
    deepest.name = "deepest"
    add_object(deepest)
    parent.add_object(deepest)
    return bag, deepest


class TestContentsSearch:
    def test_search_basics(self, global_test_env):
        """Test simple name matching."""
        obj = Object()
        obj.id = 0
        obj.name = "sword"
        add_object(obj)

        container = Object()
        container.id = 1
        container.name = "container"
        add_object(container)
        container.add_object(obj)

        results = search(container, "sword")
        assert len(results) == 1
        assert results[0] == obj

    def test_search_alias(self, global_test_env):
        """Test searching by alias."""
        obj = Object()
        obj.id = 0
        obj.name = "longsword"
        obj.aliases = ["sword", "blade"]
        add_object(obj)

        container = Object()
        container.id = 1
        container.name = "container"
        add_object(container)
        container.add_object(obj)

        results = search(container, "blade")
        assert len(results) == 1
        assert results[0] == obj

    def test_search_index(self, global_test_env):
        """Test indexing ('sword 2')."""
        obj1 = Object()
        obj1.id = 0
        obj1.name = "sword"
        add_object(obj1)

        obj2 = Object()
        obj2.id = 1
        obj2.name = "sword"
        add_object(obj2)

        container = Object()
        container.id = 2
        container.name = "container"
        add_object(container)
        container.add_object(obj1)
        container.add_object(obj2)

        results = search(container, "sword 1")
        assert len(results) == 1
        assert results[0] == obj1

        results = search(container, "sword 2")
        assert len(results) == 1
        assert results[0] == obj2

    def test_search_all(self, global_test_env):
        """Test 'all' keyword."""
        obj1 = Object()
        obj1.id = 0
        obj1.name = "coin"
        add_object(obj1)

        obj2 = Object()
        obj2.id = 1
        obj2.name = "coin"
        add_object(obj2)

        obj3 = Object()
        obj3.id = 2
        obj3.name = "gem"
        add_object(obj3)

        container = Object()
        container.id = 3
        container.name = "bag"
        add_object(container)
        container.add_object(obj1)
        container.add_object(obj2)
        container.add_object(obj3)

        results = search(container, "all coin")
        assert len(results) == 2
        assert obj1 in results
        assert obj2 in results
        assert obj3 not in results

    def test_search_count(self, global_test_env):
        """Test specific counts ('2 coin')."""
        obj1 = Object()
        obj1.id = 0
        obj1.name = "coin"
        add_object(obj1)

        obj2 = Object()
        obj2.id = 1
        obj2.name = "coin"
        add_object(obj2)

        obj3 = Object()
        obj3.id = 2
        obj3.name = "coin"
        add_object(obj3)

        container = Object()
        container.id = 3
        container.name = "bag"
        add_object(container)
        container.add_object(obj1)
        container.add_object(obj2)
        container.add_object(obj3)

        results = search(container, "2 coin")
        assert len(results) == 2

    def test_search_id(self, global_test_env):
        """Test ID searching."""
        obj = Object()
        obj.id = 42
        obj.name = "unique"
        add_object(obj)
        unique_id = obj.id

        container = Object()
        container.id = 1
        container.name = "world"
        add_object(container)
        container.add_object(obj)

        results = search(container, f"#{unique_id}")
        assert len(results) == 1
        assert results[0] == obj

    def test_search_self(self, global_test_env):
        """Test 'me' matching."""
        me = Object()
        me.id = 0
        me.name = "Hero"
        add_object(me)

        results = search(me, "me")
        assert len(results) == 1
        assert results[0] == me

        results = search(me, "Hero")
        assert len(results) == 1
        assert results[0] == me

    def test_search_plurals(self, global_test_env):
        """Test plural handling."""
        obj = Object()
        obj.id = 0
        obj.name = "sword"
        add_object(obj)

        container = Object()
        container.id = 1
        container.name = "chest"
        add_object(container)
        container.add_object(obj)

        results = search(container, "swords")
        assert len(results) == 1
        assert results[0] == obj

    def test_search_recursive_finds_nested(self, global_test_env):
        """Default recursive=True descends into containers to find nested items."""
        bag, coin, pouch, sword, box, gem = _build_nested()
        results = search(bag, "sword")
        assert results == [sword]

    def test_search_recursive_false_stays_flat(self, global_test_env):
        """recursive=False only looks at bag's direct contents; sword is nested -> []."""
        bag, coin, pouch, sword, box, gem = _build_nested()
        results = search(bag, "sword", recursive=False)
        assert results == []
        assert search(bag, "coin", recursive=False) == [coin]

    def test_search_skips_non_container(self, global_test_env):
        """A child without is_container is not descended into; gem inside box is hidden."""
        bag, coin, pouch, sword, box, gem = _build_nested()
        assert search(bag, "gem") == []

    def test_search_depth_limit_caps_recursion(self, global_test_env, monkeypatch):
        """MAX_SEARCH_DEPTH stops descent; items beyond it are not found, shallow ones are."""
        monkeypatch.setattr("atheriz.objects.contents.MAX_SEARCH_DEPTH", 3)
        bag, deepest = _build_chain(4)
        assert search(bag, "deepest") == []

        coin = Object()
        coin.id = 999
        coin.name = "coin"
        add_object(coin)
        bag.add_object(coin)
        assert search(bag, "coin") == [coin]

    def test_search_recursion_error_is_caught(self, global_test_env, monkeypatch):
        """If Python's own stack blows before the depth guard, RecursionError is swallowed."""
        monkeypatch.setattr("atheriz.objects.contents.MAX_SEARCH_DEPTH", 10_000)

        original_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(60)
        try:
            bag, deepest = _build_chain(80)
            result = search(bag, "deepest")
            assert isinstance(result, list)
        finally:
            sys.setrecursionlimit(original_limit)

    def test_search_by_index_with_sparse_positions(self, global_test_env):
        """Searching 'sword 2' with non-consecutive matches must not KeyError."""
        container = Object()
        container.id = 100
        container.name = "chest"
        add_object(container)

        objs = []
        for i in range(5):
            o = Object()
            o.id = 200 + i
            if i in (1, 4):
                o.name = "sword"
            else:
                o.name = "shield"
            add_object(o)
            container.add_object(o)
            objs.append(o)

        results = search(container, "sword 2")
        assert len(results) == 1
        assert results[0] == objs[4]

        results = search(container, "sword 1")
        assert len(results) == 1
        assert results[0] == objs[1]

    def test_singular_words_not_treated_as_plurals(self, global_test_env):
        """Words like 'bus', 'glass' should not have their 's' stripped."""
        container = Object()
        container.id = 500
        container.name = "station"
        add_object(container)

        bus = Object()
        bus.id = 501
        bus.name = "bus"
        add_object(bus)
        container.add_object(bus)

        glass = Object()
        glass.id = 502
        glass.name = "glass"
        add_object(glass)
        container.add_object(glass)

        photo1 = Object()
        photo1.id = 503
        photo1.name = "photo"
        add_object(photo1)
        container.add_object(photo1)

        photo2 = Object()
        photo2.id = 504
        photo2.name = "photo"
        add_object(photo2)
        container.add_object(photo2)

        results = search(container, "bus")
        assert len(results) == 1
        assert results[0] == bus

        results = search(container, "glass")
        assert len(results) == 1
        assert results[0] == glass

        results = search(container, "photos")
        assert len(results) == 2
        assert photo1 in results
        assert photo2 in results


class TestSearchDupes:
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


class TestSearchDoesNotReturnContainerItself:
    def test_search_does_not_return_container_itself(self, global_test_env):
        bag = Object.create(None, "bag", is_container=True)
        bag.is_container = True
        coin = Object.create(None, "coin", is_item=True)
        coin.move_to(bag)
        results = bag.search("bag")
        assert bag not in results, "search(bag,'bag') should not return container itself"
        assert results == []

    def test_search_container_name_does_not_shadow_contents(self, global_test_env):
        bag = Object.create(None, "bag", is_container=True)
        bag.is_container = True
        bag2 = Object.create(None, "bag", is_item=True)
        bag2.move_to(bag)
        results = bag.search("bag")
        assert bag not in results
        assert bag2 in results or results == [bag2]

    def test_search_me_still_returns_self(self, global_test_env):
        hero = Object.create(None, "Hero", is_pc=True)
        results = hero.search("me")
        assert hero in results
        results2 = hero.search("hero")
        assert hero in results2


class TestSearchPluralAndSubstringEdges:
    def test_search_all_alone_returns_all_contents(self, global_test_env):
        bag = Object.create(None, "bag2", is_container=True)
        bag.is_container = True
        a = Object.create(None, "apple", is_item=True)
        b = Object.create(None, "banana", is_item=True)
        a.move_to(bag)
        b.move_to(bag)
        results = bag.search("all")
        assert len(results) == 2, f"'all' alone should return all contents, got {results}"
        assert a in results and b in results

    def test_search_substring_does_not_match_caterpillar(self, global_test_env):
        bag = Object.create(None, "bag3", is_container=True)
        bag.is_container = True
        cat = Object.create(None, "cat", is_item=True)
        caterpillar = Object.create(None, "caterpillar", is_item=True)
        caterpillar.move_to(bag)
        results = bag.search("cat")
        assert cat not in results or caterpillar not in results
        assert caterpillar not in results, "'cat' should not match 'caterpillar' via substring"
        cat.move_to(bag)
        results2 = bag.search("cat")
        assert cat in results2
        assert caterpillar not in results2

    def test_search_split_multiple_spaces(self, global_test_env):
        bag = Object.create(None, "bag4", is_container=True)
        bag.is_container = True
        sword = Object.create(None, "sword", is_item=True)
        sword.move_to(bag)
        results = bag.search("sword  ")
        assert sword in results or results == [sword]
        results2 = bag.search("  sword")
        assert sword in results2
        results3 = bag.search("sword  2")
        assert results3 == []

    def test_search_plural_cat_vs_caterpillar(self, global_test_env):
        bag = Object.create(None, "bag5", is_container=True)
        bag.is_container = True
        caterpillar = Object.create(None, "caterpillar", is_item=True)
        caterpillar.move_to(bag)
        results = bag.search("cats")
        assert caterpillar not in results, "'cats' plural should not match caterpillar"
