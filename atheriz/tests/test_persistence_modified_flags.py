"""Regression tests for object/tick persistence mechanics.

The engine only persists objects whose ``is_modified`` is True, and clears the
flag once the object has actually been committed to the database. These tests
encode that contract. They currently FAIL against the buggy save path and
should pass once the persistence logic is fixed.

Guides:
- ``save_objects()`` must only persist objects with ``is_modified=True``.
- A failed (rolled-back) save must NOT leave any object marked clean.
- Attaching scripts / adding contents in bulk must mark the owner modified.
- A single corrupt row in the objects table must not brick the whole load.
"""

import pytest

from atheriz import database_setup
from atheriz.objects.base_obj import Object
from atheriz.objects.base_script import Script
from atheriz.globals.objects import _ALL_OBJECTS, get, load_objects, save_objects


def test_rollback_save_preserves_dirty_flags(global_test_env, monkeypatch):
    """A failed save must leave every not-persisted object marked dirty.

    save_objects() clears ``is_modified`` inside ``get_save_ops_clearing()``
    *before* the transaction COMMITs. When a later object in the same run
    fails, the ROLLBACK leaves earlier objects with ``is_modified=False``
    despite their data never having been committed -- those changes would be
    silently lost on the next save, so save_objects() re-marks every attempted
    object dirty on the rollback path.
    """
    obj1 = Object.create(None, "one")
    obj2 = Object.create(None, "two")
    save_objects()
    assert obj1.is_modified is False
    assert obj2.is_modified is False

    obj1.name = "changed-one"
    obj2.name = "changed-two"
    assert obj1.is_modified is True
    assert obj2.is_modified is True

    def boom():
        raise RuntimeError("injected serialization failure")

    monkeypatch.setattr(obj2, "get_save_ops_clearing", boom)

    with pytest.raises(RuntimeError):
        save_objects()

    # Neither object was committed; both must still be dirty.
    assert obj1.is_modified is True
    assert obj2.is_modified is True


def test_script_attachment_marks_object_modified(global_test_env):
    """Attaching a Script must mark the owning object for persistence."""
    obj = Object.create(None, "HarborMaster")
    save_objects()
    assert obj.is_modified is False

    script = Script.create(obj, "PatternScript")
    obj.add_script(script)

    assert obj.is_modified is True

    # and the association survives a restart
    obj_id = obj.id
    script_id = script.id
    save_objects()
    database_setup._DATABASE.close()
    database_setup._CLOSED = False
    _ALL_OBJECTS.clear()
    load_objects()
    reloaded = get(obj_id)
    assert reloaded is not None
    assert script_id in reloaded[0].scripts


def test_script_removal_marks_object_modified(global_test_env):
    """Detaching a Script must mark the owning object for persistence:
    the removal is a content change like the attachment is."""
    obj = Object.create(None, "HarborMaster")
    script = Script.create(obj, "PatternScript")
    obj.add_script(script)
    save_objects()
    assert obj.is_modified is False

    obj.remove_script(script)

    assert obj.is_modified is True


def test_bulk_add_contents_marks_container_modified(global_test_env):
    """Bulk-adding contents must mark the container as modified.

    (add_objects() mutates ``_contents`` in place but never sets
    ``is_modified``, so a clean container silently loses the new contents on
    the next save checkpoint.)
    """
    bag = Object.create(None, "Bag", is_container=True)
    sword = Object.create(None, "Sword")
    save_objects()
    assert bag.is_modified is False

    bag.add_objects([sword])

    assert bag.is_modified is True

    # and the association survives a restart
    bag_id = bag.id
    save_objects()
    database_setup._DATABASE.close()
    database_setup._CLOSED = False
    _ALL_OBJECTS.clear()
    load_objects()
    reloaded = get(bag_id)
    assert reloaded is not None
    assert sword.id in reloaded[0]._contents


def test_node_bulk_add_contents_marks_node_modified(global_test_env):
    """Bulk-adding contents to a node must mark the node (and each added
    object) modified, matching Object.add_objects semantics."""
    from atheriz.globals.node import NodeHandler
    from atheriz.objects.nodes import Node
    from atheriz.utils import Coord

    nh = NodeHandler()
    node = Node(coord=Coord("test", 7, 7, 0))
    nh.add_node(node)
    obj = Object.create(None, "Sword")
    node.is_modified = False
    obj.is_modified = False

    node.add_objects([obj])

    assert node.is_modified is True
    assert obj.is_modified is True


def test_corrupt_row_skipped_on_load(global_test_env):
    """load_objects must skip an un-deserializable row instead of crashing.

    A single bad blob currently aborts the whole boot because there is no
    per-row guard (contrast NodeHandler.load).
    """
    obj = Object.create(None, "goodguy")
    save_objects()

    db = database_setup.get_database()
    with db.lock:
        cur = db.connection.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)",
            (777777, b"this is not a dill pickle"),
        )
        db.connection.commit()

    _ALL_OBJECTS.clear()
    load_objects()

    assert get(obj.id) is not None
    assert get(obj.id)[0].name == "goodguy"
    assert get(777777) == []