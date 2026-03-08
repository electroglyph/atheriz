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
