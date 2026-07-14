from atheriz.objects.base_obj import Object
from atheriz.objects.contents import search
from atheriz.globals.objects import add_object
from atheriz.globals import objects
import pytest


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear the objects registry before each test."""
    objects._ALL_OBJECTS.clear()
    yield


def test_search_basics():
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

    # Search in container
    results = search(container, "sword")
    assert len(results) == 1
    assert results[0] == obj


def test_search_alias():
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


def test_search_index():
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

    # "sword 1" -> first one
    results = search(container, "sword 1")
    assert len(results) == 1
    assert results[0] == obj1

    # "sword 2" -> second one
    results = search(container, "sword 2")
    assert len(results) == 1
    assert results[0] == obj2


def test_search_all():
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


def test_search_count():
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


def test_search_id():
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


def test_search_self():
    """Test 'me' matching."""
    me = Object()
    me.id = 0
    me.name = "Hero"
    add_object(me)

    # search(obj, "me") returns [obj]
    results = search(me, "me")
    assert len(results) == 1
    assert results[0] == me

    # search(obj, obj.name) returns [obj]
    results = search(me, "Hero")
    assert len(results) == 1
    assert results[0] == me


def test_search_plurals():
    """Test plural handling."""
    # Assuming the search logic handles 'swords' -> 'sword'
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


# ---------------------------------------------------------------------------
# recursive search (nested containers via is_container)
# ---------------------------------------------------------------------------


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
    # is_container stays False (default)
    add_object(box)
    bag.add_object(box)

    gem = Object()
    gem.id = 6
    gem.name = "gem"
    add_object(gem)
    box.add_object(gem)

    return bag, coin, pouch, sword, box, gem


def test_search_recursive_finds_nested():
    """Default recursive=True descends into containers to find nested items."""
    bag, coin, pouch, sword, box, gem = _build_nested()
    results = search(bag, "sword")
    assert results == [sword]


def test_search_recursive_false_stays_flat():
    """recursive=False only looks at bag's direct contents; sword is nested -> []."""
    bag, coin, pouch, sword, box, gem = _build_nested()
    results = search(bag, "sword", recursive=False)
    assert results == []
    # direct contents are still matchable when flat
    assert search(bag, "coin", recursive=False) == [coin]


def test_search_skips_non_container():
    """A child without is_container is not descended into; gem inside box is hidden."""
    bag, coin, pouch, sword, box, gem = _build_nested()
    assert search(bag, "gem") == []


# ---------------------------------------------------------------------------
# depth limit / stack-overflow guard
# ---------------------------------------------------------------------------


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


def test_search_depth_limit_caps_recursion(monkeypatch):
    """MAX_SEARCH_DEPTH stops descent; items beyond it are not found, shallow ones are."""
    monkeypatch.setattr("atheriz.objects.contents.MAX_SEARCH_DEPTH", 3)
    # chain: bag -> c1 -> c2 -> c3 -> c4 -> deepest (deepest sits at depth 4)
    bag, deepest = _build_chain(4)
    assert search(bag, "deepest") == []

    # a shallow item is still matchable
    coin = Object()
    coin.id = 999
    coin.name = "coin"
    add_object(coin)
    bag.add_object(coin)
    assert search(bag, "coin") == [coin]


def test_search_recursion_error_is_caught(monkeypatch):
    """If Python's own stack blows before the depth guard, RecursionError is swallowed."""
    import sys

    # Raise the depth ceiling so the interpreter recursion limit fires first.
    monkeypatch.setattr("atheriz.objects.contents.MAX_SEARCH_DEPTH", 10_000)

    original_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(60)
    try:
        # Chain longer than the (lowered) recursion limit; must not raise.
        bag, deepest = _build_chain(80)
        result = search(bag, "deepest")
        assert isinstance(result, list)
    finally:
        sys.setrecursionlimit(original_limit)
