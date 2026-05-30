import dill
import pytest
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import add_object, remove_object, get_by_tag
from atheriz.globals import objects as obj_singleton


def _make_obj(obj_id: int, tags: set[str]) -> Object:
    obj = Object()
    obj.id = obj_id
    obj.tags = tags
    add_object(obj)
    return obj


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_tags_survive_serialization():
    """Tags set on an Object must be preserved through dill round-trip."""
    obj = Object()
    obj.id = 1
    obj.tags = {"warrior", "hero"}

    serialized = dill.dumps(obj)
    restored = dill.loads(serialized)

    assert object.__getattribute__(restored, "tags") == {"warrior", "hero"}


def test_empty_tags_survive_serialization():
    """An empty tags set must deserialize as an empty set, not missing."""
    obj = Object()
    obj.id = 2
    obj.tags = set()

    serialized = dill.dumps(obj)
    restored = dill.loads(serialized)

    result = object.__getattribute__(restored, "tags")
    assert isinstance(result, set)
    assert len(result) == 0


def test_tags_default_is_empty_set():
    """Flags.__init__ must initialise tags to an empty set."""
    obj = Object()
    assert isinstance(obj.tags, set)
    assert len(obj.tags) == 0


# ---------------------------------------------------------------------------
# get_by_tag – single string
# ---------------------------------------------------------------------------

def test_get_by_tag_single_match(global_test_env):
    obj = _make_obj(10, {"villain"})
    result = get_by_tag("villain")
    assert obj in result


def test_get_by_tag_single_no_match(global_test_env):
    _make_obj(11, {"hero"})
    result = get_by_tag("villain")
    assert result == []


def test_get_by_tag_single_multiple_objects(global_test_env):
    a = _make_obj(12, {"knight"})
    b = _make_obj(13, {"knight", "mage"})
    c = _make_obj(14, {"mage"})

    result = get_by_tag("knight")
    assert a in result
    assert b in result
    assert c not in result


# ---------------------------------------------------------------------------
# get_by_tag – list of tags (ANY match)
# ---------------------------------------------------------------------------

def test_get_by_tag_list_any_match(global_test_env):
    a = _make_obj(20, {"warrior"})
    b = _make_obj(21, {"mage"})
    c = _make_obj(22, {"bard"})

    result = get_by_tag(["warrior", "mage"])
    assert a in result
    assert b in result
    assert c not in result


def test_get_by_tag_list_no_match(global_test_env):
    _make_obj(23, {"rogue"})
    result = get_by_tag(["warrior", "mage"])
    assert result == []


def test_get_by_tag_list_overlap(global_test_env):
    """Object with both queried tags must appear exactly once."""
    obj = _make_obj(24, {"warrior", "mage"})
    result = get_by_tag(["warrior", "mage"])
    assert result.count(obj) == 1


def test_get_by_tag_empty_list(global_test_env):
    """Searching for an empty list of tags should return nothing."""
    _make_obj(25, {"warrior"})
    result = get_by_tag([])
    assert result == []


def test_get_by_tag_all(global_test_env):
    a = _make_obj(26, {"warrior", "hero"})
    b = _make_obj(27, {"warrior"})
    c = _make_obj(28, {"mage"})
    
    # Must have both
    result = get_by_tag(["warrior", "hero"], all=True)
    assert a in result
    assert b not in result
    assert c not in result
    
    # Must have warrior
    result = get_by_tag(["warrior"], all=True)
    assert a in result
    assert b in result
    assert c not in result
    
    # Empty set requirement trivially satisfied by all objects
    result = get_by_tag([], all=True)
    assert a in result
    assert b in result
    assert c in result


# ---------------------------------------------------------------------------
# get_by_tag – objects without tags attribute (legacy deserialization guard)
# ---------------------------------------------------------------------------

def test_get_by_tag_missing_tags_attr(global_test_env):
    """Objects that somehow lack a tags attribute must not crash get_by_tag."""
    obj = Object()
    obj.id = 30
    # Deliberately remove the tags attribute to simulate an old pickled object
    object.__delattr__(obj, "tags")
    add_object(obj)

    # Should not raise; the missing-attribute object must simply be excluded
    result = get_by_tag("warrior")
    assert obj not in result


# ---------------------------------------------------------------------------
# add_tag
# ---------------------------------------------------------------------------

def test_add_tag_single_string():
    obj = Object()
    obj.add_tag("warrior")
    assert "warrior" in obj.tags


def test_add_tag_list():
    obj = Object()
    obj.add_tag(["warrior", "mage"])
    assert "warrior" in obj.tags
    assert "mage" in obj.tags


def test_add_tag_set():
    obj = Object()
    obj.add_tag({"rogue", "bard"})
    assert "rogue" in obj.tags
    assert "bard" in obj.tags


def test_add_tag_idempotent():
    """Adding the same tag twice must not duplicate it."""
    obj = Object()
    obj.add_tag("hero")
    obj.add_tag("hero")
    assert obj.tags.count("hero") if hasattr(obj.tags, "count") else len([t for t in obj.tags if t == "hero"]) == 1


def test_add_tag_sets_is_modified():
    obj = Object()
    obj.is_modified = False
    obj.add_tag("knight")
    assert obj.is_modified is True


def test_add_tag_visible_to_get_by_tag(global_test_env):
    obj = Object()
    obj.id = 40
    add_object(obj)
    obj.add_tag("paladin")
    assert obj in get_by_tag("paladin")


# ---------------------------------------------------------------------------
# remove_tag
# ---------------------------------------------------------------------------

def test_remove_tag_single_string():
    obj = Object()
    obj.add_tag(["warrior", "mage"])
    obj.remove_tag("warrior")
    assert "warrior" not in obj.tags
    assert "mage" in obj.tags


def test_remove_tag_list():
    obj = Object()
    obj.add_tag(["warrior", "mage", "bard"])
    obj.remove_tag(["warrior", "mage"])
    assert "warrior" not in obj.tags
    assert "mage" not in obj.tags
    assert "bard" in obj.tags


def test_remove_tag_set():
    obj = Object()
    obj.add_tag({"a", "b", "c"})
    obj.remove_tag({"a", "b"})
    assert "a" not in obj.tags
    assert "b" not in obj.tags
    assert "c" in obj.tags


def test_remove_tag_missing_is_silent():
    """Removing a tag that doesn't exist must not raise."""
    obj = Object()
    obj.remove_tag("nonexistent")  # should not raise


def test_remove_tag_sets_is_modified():
    obj = Object()
    obj.add_tag("knight")
    obj.is_modified = False
    obj.remove_tag("knight")
    assert obj.is_modified is True


def test_remove_tag_invisible_to_get_by_tag(global_test_env):
    obj = Object()
    obj.id = 41
    obj.add_tag("necromancer")
    add_object(obj)
    assert obj in get_by_tag("necromancer")
    obj.remove_tag("necromancer")
    assert obj not in get_by_tag("necromancer")


# ---------------------------------------------------------------------------
# has_tag
# ---------------------------------------------------------------------------

def test_has_tag_single_string():
    obj = Object()
    obj.add_tag("warrior")
    assert obj.has_tag("warrior") is True
    assert obj.has_tag("mage") is False


def test_has_tag_list():
    obj = Object()
    obj.add_tag(["warrior", "mage"])
    assert obj.has_tag(["warrior"]) is True
    assert obj.has_tag(["warrior", "rogue"]) is True  # ANY match
    assert obj.has_tag(["rogue", "bard"]) is False


def test_has_tag_set():
    obj = Object()
    obj.add_tag("warrior")
    assert obj.has_tag({"warrior", "mage"}) is True
    assert obj.has_tag({"mage"}) is False


def test_has_tag_all():
    obj = Object()
    obj.add_tag(["warrior", "hero"])
    assert obj.has_tag(["warrior", "hero"], all=True) is True
    assert obj.has_tag(["warrior"], all=True) is True
    assert obj.has_tag(["warrior", "mage"], all=True) is False
    assert obj.has_tag(["mage"], all=True) is False
    assert obj.has_tag([], all=True) is True  # empty set is a subset of anything
