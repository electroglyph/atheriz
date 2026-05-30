import dill
import pytest
from atheriz.utils import Coord
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel
from atheriz.objects.nodes import Node
from atheriz.objects.base_script import Script
from atheriz.globals.objects import add_object, get_by_tag
from atheriz.globals import objects as obj_singleton


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

ENTITY_TYPES = ["object", "account", "channel", "node", "script"]


def _make_instance(entity_type: str, unique_x: int = 0):
    """Return a fresh, unregistered instance of the requested entity type."""
    if entity_type == "object":
        return Object()
    elif entity_type == "account":
        return Account()
    elif entity_type == "channel":
        return Channel()
    elif entity_type == "node":
        return Node(coord=Coord("test", unique_x, 0, 0))
    elif entity_type == "script":
        return Script()
    raise ValueError(f"Unknown entity_type: {entity_type}")


@pytest.fixture(params=ENTITY_TYPES)
def tagged_obj(request):
    """Yields a fresh, unregistered instance of each taggable type."""
    return _make_instance(request.param)


def _make_obj(obj_id: int, tags: set[str], entity_type: str = "object") -> object:
    """Create, tag, and register an entity of the given type."""
    obj = _make_instance(entity_type, unique_x=obj_id)
    obj.id = obj_id
    obj.tags = tags
    add_object(obj)
    return obj


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_tags_survive_serialization(entity_type):
    """Tags set on any taggable object must be preserved through dill round-trip."""
    obj = _make_instance(entity_type, unique_x=1)
    obj.id = 1
    obj.tags = {"warrior", "hero"}

    serialized = dill.dumps(obj)
    restored = dill.loads(serialized)

    assert object.__getattribute__(restored, "tags") == {"warrior", "hero"}


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_empty_tags_survive_serialization(entity_type):
    """An empty tags set must deserialize as an empty set, not missing."""
    obj = _make_instance(entity_type, unique_x=2)
    obj.id = 2
    obj.tags = set()

    serialized = dill.dumps(obj)
    restored = dill.loads(serialized)

    result = object.__getattribute__(restored, "tags")
    assert isinstance(result, set)
    assert len(result) == 0


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_tags_default_is_empty_set(entity_type):
    """Flags.__init__ must initialise tags to an empty set for every taggable type."""
    obj = _make_instance(entity_type)
    assert isinstance(obj.tags, set)
    assert len(obj.tags) == 0


# ---------------------------------------------------------------------------
# get_by_tag – single string
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_single_match(global_test_env, entity_type):
    obj = _make_obj(10, {"villain"}, entity_type)
    result = get_by_tag("villain")
    assert obj in result


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_single_no_match(global_test_env, entity_type):
    _make_obj(11, {"hero"}, entity_type)
    result = get_by_tag("villain")
    assert result == []


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_single_multiple_objects(global_test_env, entity_type):
    a = _make_obj(12, {"knight"}, entity_type)
    b = _make_obj(13, {"knight", "mage"}, entity_type)
    c = _make_obj(14, {"mage"}, entity_type)

    result = get_by_tag("knight")
    assert a in result
    assert b in result
    assert c not in result


# ---------------------------------------------------------------------------
# get_by_tag – list of tags (ANY match)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_list_any_match(global_test_env, entity_type):
    a = _make_obj(20, {"warrior"}, entity_type)
    b = _make_obj(21, {"mage"}, entity_type)
    c = _make_obj(22, {"bard"}, entity_type)

    result = get_by_tag(["warrior", "mage"])
    assert a in result
    assert b in result
    assert c not in result


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_list_no_match(global_test_env, entity_type):
    _make_obj(23, {"rogue"}, entity_type)
    result = get_by_tag(["warrior", "mage"])
    assert result == []


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_list_overlap(global_test_env, entity_type):
    """Entity with both queried tags must appear exactly once."""
    obj = _make_obj(24, {"warrior", "mage"}, entity_type)
    result = get_by_tag(["warrior", "mage"])
    assert result.count(obj) == 1


def test_get_by_tag_empty_list(global_test_env):
    """Searching for an empty list of tags should return nothing."""
    _make_obj(25, {"warrior"})
    result = get_by_tag([])
    assert result == []


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_get_by_tag_all(global_test_env, entity_type):
    a = _make_obj(26, {"warrior", "hero"}, entity_type)
    b = _make_obj(27, {"warrior"}, entity_type)
    c = _make_obj(28, {"mage"}, entity_type)

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
    object.__delattr__(obj, "tags")
    add_object(obj)

    result = get_by_tag("warrior")
    assert obj not in result


# ---------------------------------------------------------------------------
# add_tag
# ---------------------------------------------------------------------------

def test_add_tag_single_string(tagged_obj):
    tagged_obj.add_tag("warrior")
    assert "warrior" in tagged_obj.tags


def test_add_tag_list(tagged_obj):
    tagged_obj.add_tag(["warrior", "mage"])
    assert "warrior" in tagged_obj.tags
    assert "mage" in tagged_obj.tags


def test_add_tag_set(tagged_obj):
    tagged_obj.add_tag({"rogue", "bard"})
    assert "rogue" in tagged_obj.tags
    assert "bard" in tagged_obj.tags


def test_add_tag_idempotent(tagged_obj):
    """Adding the same tag twice must not duplicate it (sets are deduplicated)."""
    tagged_obj.add_tag("hero")
    tagged_obj.add_tag("hero")
    assert len([t for t in tagged_obj.tags if t == "hero"]) == 1


def test_add_tag_sets_is_modified(tagged_obj):
    tagged_obj.is_modified = False
    tagged_obj.add_tag("knight")
    assert tagged_obj.is_modified is True


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_add_tag_visible_to_get_by_tag(global_test_env, entity_type):
    obj = _make_instance(entity_type, unique_x=40)
    obj.id = 40
    add_object(obj)
    obj.add_tag("paladin")
    assert obj in get_by_tag("paladin")


# ---------------------------------------------------------------------------
# remove_tag
# ---------------------------------------------------------------------------

def test_remove_tag_single_string(tagged_obj):
    tagged_obj.add_tag(["warrior", "mage"])
    tagged_obj.remove_tag("warrior")
    assert "warrior" not in tagged_obj.tags
    assert "mage" in tagged_obj.tags


def test_remove_tag_list(tagged_obj):
    tagged_obj.add_tag(["warrior", "mage", "bard"])
    tagged_obj.remove_tag(["warrior", "mage"])
    assert "warrior" not in tagged_obj.tags
    assert "mage" not in tagged_obj.tags
    assert "bard" in tagged_obj.tags


def test_remove_tag_set(tagged_obj):
    tagged_obj.add_tag({"a", "b", "c"})
    tagged_obj.remove_tag({"a", "b"})
    assert "a" not in tagged_obj.tags
    assert "b" not in tagged_obj.tags
    assert "c" in tagged_obj.tags


def test_remove_tag_missing_is_silent(tagged_obj):
    """Removing a tag that doesn't exist must not raise."""
    tagged_obj.remove_tag("nonexistent")


def test_remove_tag_sets_is_modified(tagged_obj):
    tagged_obj.add_tag("knight")
    tagged_obj.is_modified = False
    tagged_obj.remove_tag("knight")
    assert tagged_obj.is_modified is True


@pytest.mark.parametrize("entity_type", ENTITY_TYPES)
def test_remove_tag_invisible_to_get_by_tag(global_test_env, entity_type):
    obj = _make_instance(entity_type, unique_x=41)
    obj.id = 41
    obj.add_tag("necromancer")
    add_object(obj)
    assert obj in get_by_tag("necromancer")
    obj.remove_tag("necromancer")
    assert obj not in get_by_tag("necromancer")


# ---------------------------------------------------------------------------
# has_tag
# ---------------------------------------------------------------------------

def test_has_tag_single_string(tagged_obj):
    tagged_obj.add_tag("warrior")
    assert tagged_obj.has_tag("warrior") is True
    assert tagged_obj.has_tag("mage") is False


def test_has_tag_list(tagged_obj):
    tagged_obj.add_tag(["warrior", "mage"])
    assert tagged_obj.has_tag(["warrior"]) is True
    assert tagged_obj.has_tag(["warrior", "rogue"]) is True  # ANY match
    assert tagged_obj.has_tag(["rogue", "bard"]) is False


def test_has_tag_set(tagged_obj):
    tagged_obj.add_tag("warrior")
    assert tagged_obj.has_tag({"warrior", "mage"}) is True
    assert tagged_obj.has_tag({"mage"}) is False


def test_has_tag_all(tagged_obj):
    tagged_obj.add_tag(["warrior", "hero"])
    assert tagged_obj.has_tag(["warrior", "hero"], all=True) is True
    assert tagged_obj.has_tag(["warrior"], all=True) is True
    assert tagged_obj.has_tag(["warrior", "mage"], all=True) is False
    assert tagged_obj.has_tag(["mage"], all=True) is False
    assert tagged_obj.has_tag([], all=True) is True  # empty set is a subset of anything
