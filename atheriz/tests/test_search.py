import pytest
from atheriz.singletons import objects
from atheriz.utils import get_import_path


class MockObj:
    def __init__(self, id):
        self.id = id


@pytest.fixture(autouse=True)
def clear_registry():
    objects._ALL_OBJECTS.clear()


def test_search_bad():
    """Test searching with no parameters returns empty list."""
    assert objects.get(-1) == []
    assert objects.get([-1]) == []


def test_search_by_id():
    """Test searching by ID only."""
    obj = MockObj(1)
    objects.add_object(obj)

    # Found
    results = objects.get(1)
    assert len(results) == 1
    assert results[0] == obj

    # Not found
    results = objects.get(999)
    assert results == []


# def test_search_by_path():
#     """Test searching by import path."""
#     obj = MockObj(2)
#     objects.add_object(obj)
#     path = get_import_path(obj)

#     results = objects.get_by_type(path)
#     assert len(results) == 1
#     assert results[0] == obj


# def test_search_by_path_multiple():
#     """Test finding multiple objects by path."""
#     obj1 = MockObj(4)
#     objects.add_object(obj1)
#     obj2 = MockObj(5)
#     objects.add_object(obj2)
#     path = get_import_path(obj1)

#     # first=False should return all
#     results = objects.get_by_type(path)
#     assert len(results) == 2
#     assert obj1 in results
#     assert obj2 in results


def test_search_ids():
    """Test searching by list of IDs."""
    obj1 = MockObj(10)
    obj2 = MockObj(11)
    obj3 = MockObj(12)
    objects.add_object(obj1)
    objects.add_object(obj2)
    objects.add_object(obj3)

    # Search for subset
    results = objects.get([10, 12])
    assert len(results) == 2
    assert obj1 in results
    assert obj3 in results
    assert obj2 not in results

    # # Search with path
    # path = get_import_path(obj1)
    # results = objects.get_by_type(path)
    # assert len(results) == 3
    # assert obj1 in results
    # assert obj2 in results
    # assert obj3 in results

    # # Search with wrong path
    # results = objects.get_by_type("wrong.path")
    # assert len(results) == 0


def test_filter_by():
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

    # Filter by is_active
    results = objects.filter_by(lambda x: getattr(x, "is_active", False))
    assert len(results) == 2
    assert obj1 in results
    assert obj3 in results
    assert obj2 not in results
