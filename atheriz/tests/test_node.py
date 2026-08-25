import pytest
import dill
from atheriz.utils import Coord
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink, Transition
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_door import Door
from atheriz.globals import objects as obj_singleton
from atheriz import settings
from pathlib import Path
import shutil




# ==================== NodeLink Tests ====================


def test_nodelink_init():
    link = NodeLink(name="north", coord=Coord("TestArea", 0, 1, 0), aliases=["n"])
    assert link.name == "north"
    assert link.coord == Coord("TestArea", 0, 1, 0)
    assert link.aliases == ["n"]


def test_nodelink_str():
    link = NodeLink(name="south", coord=Coord("TestArea", 0, 0, 0))
    s = str(link)
    assert "south" in s
    assert "TestArea" in s


# ==================== Node Tests ====================


def test_node_init():
    node = Node(coord=Coord("TestArea", 1, 2, 3), desc="A dark room")
    assert node.coord == Coord("TestArea", 1, 2, 3)
    assert node.desc == "A dark room"
    assert node.links == []


def test_node_with_links():
    link = NodeLink(name="north", coord=Coord("TestArea", 0, 1, 0))
    node = Node(coord=Coord("TestArea", 0, 0, 0), links=[link])
    assert len(node.links) == 1
    assert node.links[0].name == "north"


def test_node_add_link():
    node = Node(coord=Coord("TestArea", 0, 0, 0))
    link = NodeLink(name="east", coord=Coord("TestArea", 1, 0, 0))
    node.add_link(link)
    assert len(node.links) == 1
    assert node.links[0].name == "east"


def test_node_nouns():
    node = Node(coord=Coord("TestArea", 0, 0, 0))
    node.add_noun("fountain", "A marble fountain with clear water")
    assert node.get_noun("fountain") == "A marble fountain with clear water"
    node.remove_noun("fountain")
    assert node.get_noun("fountain") is None


def test_remove_noun_nonexistent_no_crash():
    node = Node(coord=Coord("TestArea", 0, 0, 0))
    node.remove_noun("nonexistent")


def test_node_equality():
    node1 = Node(coord=Coord("TestArea", 0, 0, 0))
    node2 = Node(coord=Coord("TestArea", 0, 0, 0))
    node3 = Node(coord=Coord("TestArea", 1, 0, 0))

    assert node1 == node1
    assert node1 != node2
    assert node1.coord == node2.coord
    assert node1 != node3


# ==================== NodeGrid Tests ====================


def test_nodegrid_init():
    grid = NodeGrid(z=5)
    assert grid.z == 5
    assert len(grid) == 0


def test_nodegrid_add_get_node():
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("TestArea", 1, 2, 0))
    grid.nodes[(1, 2)] = node

    assert len(grid) == 1
    assert grid.get_node((1, 2)) == node
    assert grid.get_node((0, 0)) is None


def test_nodegrid_clear():
    grid = NodeGrid(z=0)
    grid.nodes[(0, 0)] = Node(coord=Coord("TestArea", 0, 0, 0))
    grid.nodes[(1, 1)] = Node(coord=Coord("TestArea", 1, 1, 0))
    assert len(grid) == 2

    grid.clear()
    assert len(grid) == 0


def test_nodegrid_data():
    grid = NodeGrid(z=0)
    grid.set_data("region", "forest")
    assert grid.get_data("region") == "forest"
    assert grid.get_data("nonexistent") is None


# ==================== NodeArea Tests ====================


def test_nodearea_init():
    area = NodeArea(name="Forest", theme="nature")
    assert area.name == "Forest"
    assert area.theme == "nature"
    assert len(area) == 0


def test_nodearea_add_get_grid():
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    area.add_grid(grid)

    assert len(area) == 1
    assert area.get_grid(0) == grid
    assert grid.area == "TestArea"


def test_nodearea_remove_grid():
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    area.add_grid(grid)
    area.remove_grid(0)

    assert len(area) == 0


def test_remove_grid_nonexistent_no_crash():
    area = NodeArea(name="TestArea")
    area.remove_grid(999)


def test_nodearea_clear():
    area = NodeArea(name="TestArea")
    area.add_grid(NodeGrid(z=0))
    area.add_grid(NodeGrid(z=1))
    assert len(area) == 2

    area.clear()
    assert len(area) == 0


def test_nodearea_data():
    area = NodeArea(name="TestArea")
    area.set_data("biome", "desert")
    assert area.get_data("biome") == "desert"
    area.remove_data("biome")
    assert area.get_data("biome") is None


def test_nodearea_get_nodes():
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    node1 = Node(coord=Coord("TestArea", 0, 0, 0))
    node2 = Node(coord=Coord("TestArea", 1, 1, 0))
    grid.nodes[(0, 0)] = node1
    grid.nodes[(1, 1)] = node2
    area.add_grid(grid)

    nodes = area.get_nodes([(0, 0, 0), (1, 1, 0), (99, 99, 0)])
    assert len(nodes) == 2
    assert node1 in nodes
    assert node2 in nodes


# ==================== Transition Tests ====================


def test_transition_init():
    trans = Transition(
        from_coord=Coord("Area1", 0, 0, 0), to_coord=Coord("Area2", 0, 0, 0), from_link="north"
    )
    assert trans.from_coord == Coord("Area1", 0, 0, 0)
    assert trans.to_coord == Coord("Area2", 0, 0, 0)
    assert trans.from_link == "north"


# ==================== NodeHandler Tests ====================


def test_nodehandler_add_get_area():
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    handler.add_area(area)

    assert handler.get_area("TestArea") == area
    assert handler.get_area("Nonexistent") is None


def test_nodehandler_get_areas():
    handler = NodeHandler()
    area1 = NodeArea(name="Area1")
    area2 = NodeArea(name="Area2")
    handler.add_area(area1)
    handler.add_area(area2)

    areas = handler.get_areas()
    assert len(areas) == 2


def test_nodehandler_remove_area():
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    handler.add_area(area)
    handler.remove_area("TestArea")

    assert handler.get_area("TestArea") is None


def test_nodehandler_clear():
    handler = NodeHandler()
    handler.add_area(NodeArea(name="Area1"))
    handler.add_area(NodeArea(name="Area2"))
    handler.clear()

    assert len(handler.areas) == 0


def test_nodehandler_get_node():
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("TestArea", 5, 10, 0))
    grid.nodes[(5, 10)] = node
    area.add_grid(grid)
    handler.add_area(area)

    result = handler.get_node(Coord("TestArea", 5, 10, 0))
    assert result == node

    assert handler.get_node(Coord("TestArea", 99, 99, 0)) is None
    assert handler.get_node(Coord("NonexistentArea", 0, 0, 0)) is None


def test_nodehandler_get_nodes():
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    node1 = Node(coord=Coord("TestArea", 0, 0, 0))
    node2 = Node(coord=Coord("TestArea", 1, 1, 0))
    grid.nodes[(0, 0)] = node1
    grid.nodes[(1, 1)] = node2
    area.add_grid(grid)
    handler.add_area(area)

    nodes = handler.get_nodes([Coord("TestArea", 0, 0, 0), Coord("TestArea", 1, 1, 0)])
    assert len(nodes) == 2


def test_nodehandler_add_remove_transition():
    handler = NodeHandler()
    trans = Transition(
        from_coord=Coord("Area1", 0, 0, 0), to_coord=Coord("Area2", 0, 0, 0), from_link="north"
    )

    handler.add_transition(trans)
    assert Coord("Area2", 0, 0, 0) in handler.transitions

    handler.remove_transition(Coord("Area2", 0, 0, 0))
    assert Coord("Area2", 0, 0, 0) not in handler.transitions


def test_nodehandler_find_transitions():
    handler = NodeHandler()

    t1 = Transition(from_coord=Coord("Area1", 0, 0, 0), to_coord=Coord("Area2", 0, 0, 0), from_link="north")
    t2 = Transition(from_coord=Coord("Area1", 0, 0, 1), to_coord=Coord("Area3", 0, 0, 1), from_link="up")
    t3 = Transition(from_coord=Coord("Area2", 0, 0, 0), to_coord=Coord("Area1", 0, 0, 0), from_link="south")

    handler.add_transition(t1)
    handler.add_transition(t2)
    handler.add_transition(t3)

    # Find by from_area
    results = handler.find_transitions(from_area="Area1")
    assert len(results) == 2

    # Find by to_area
    results = handler.find_transitions(to_area="Area2")
    assert len(results) == 1


def test_find_transitions_multi_criteria():
    handler = NodeHandler()

    t1 = Transition(from_coord=Coord("A", 0, 0, 1), to_coord=Coord("B", 0, 0, 2), from_link="north")
    t2 = Transition(from_coord=Coord("A", 0, 0, 1), to_coord=Coord("C", 0, 0, 3), from_link="east")
    t3 = Transition(from_coord=Coord("D", 0, 0, 2), to_coord=Coord("E", 0, 0, 2), from_link="south")

    handler.add_transition(t1)
    handler.add_transition(t2)
    handler.add_transition(t3)

    # from_z=1 AND to_z=2 — only t1 matches both
    results = handler.find_transitions(from_z=1, to_z=2)
    assert len(results) == 1
    assert results[0] is t1

    # from_z=1 alone — t1 and t2 both match
    results = handler.find_transitions(from_z=1)
    assert len(results) == 2

    # to_z=2 alone — t1 and t3 both match
    results = handler.find_transitions(to_z=2)
    assert len(results) == 2

    # from_area + to_area combined
    results = handler.find_transitions(from_area="A", to_area="B")
    assert len(results) == 1
    assert results[0] is t1


def test_nodehandler_add_door():
    handler = NodeHandler()
    door = Door(
        from_coord=Coord("Area1", 0, 0, 0),
        to_coord=Coord("Area2", 0, 0, 0),
        from_exit="north",
        to_exit="south",
    )

    handler.add_door(door)

    # Door should be accessible from both sides
    doors_from = handler.get_doors(Coord("Area1", 0, 0, 0))
    doors_to = handler.get_doors(Coord("Area2", 0, 0, 0))

    assert "north" in doors_from
    assert "south" in doors_to
    assert doors_from["north"] == door
    assert doors_to["south"] == door


# ==================== Integration Tests ====================
# These tests require full area/grid/handler setup


def test_nodegrid_add_node_creates_transition():
    """Adding a node with a link to another area should create a transition"""
    from atheriz.globals.get import get_node_handler

    handler = get_node_handler()

    # Create two areas
    area1 = NodeArea(name="Area1")
    area2 = NodeArea(name="Area2")
    handler.add_area(area1)
    handler.add_area(area2)

    # Create grid for area1
    grid = NodeGrid(z=0)
    area1.add_grid(grid)

    # Create a node with a link to area2
    link = NodeLink(name="north", coord=Coord("Area2", 0, 0, 0))
    node = Node(coord=Coord("Area1", 0, 0, 0), links=[link])

    # Add node via grid - this should create a transition
    grid.add_node(node)

    # Verify transition was created
    assert Coord("Area2", 0, 0, 0) in handler.transitions
    trans = handler.transitions[Coord("Area2", 0, 0, 0)]
    assert trans.from_coord == Coord("Area1", 0, 0, 0)
    assert trans.from_link == "north"


def test_nodegrid_remove_node_removes_transition():
    """Removing a node with a cross-area link should remove the transition"""
    from atheriz.globals.get import get_node_handler

    handler = get_node_handler()

    # Setup areas
    area1 = NodeArea(name="Area1")
    area2 = NodeArea(name="Area2")
    handler.add_area(area1)
    handler.add_area(area2)

    grid = NodeGrid(z=0)
    area1.add_grid(grid)

    link = NodeLink(name="north", coord=Coord("Area2", 0, 0, 0))
    node = Node(coord=Coord("Area1", 0, 0, 0), links=[link])
    grid.add_node(node)

    # Verify transition exists
    assert Coord("Area2", 0, 0, 0) in handler.transitions

    # Remove the node
    grid.remove_node((0, 0))

    # Verify transition was removed
    assert Coord("Area2", 0, 0, 0) not in handler.transitions


def test_node_remove_link_removes_transition():
    """Removing a cross-area link from a node should remove the transition"""
    from atheriz.globals.get import get_node_handler

    handler = get_node_handler()

    # Setup areas
    area1 = NodeArea(name="Area1")
    area2 = NodeArea(name="Area2")
    handler.add_area(area1)
    handler.add_area(area2)

    grid = NodeGrid(z=0)
    area1.add_grid(grid)

    link = NodeLink(name="north", coord=Coord("Area2", 0, 0, 0))
    node = Node(coord=Coord("Area1", 0, 0, 0), links=[link])
    grid.add_node(node)

    # Verify transition exists
    assert Coord("Area2", 0, 0, 0) in handler.transitions

    # Remove the link from the node
    node.remove_link("north")

    # Verify transition was removed
    assert Coord("Area2", 0, 0, 0) not in handler.transitions
    assert len(node.links) == 0


def test_node_remove_link_same_area_no_transition():
    """Removing a same-area link should not try to remove transitions"""
    from atheriz.globals.get import get_node_handler

    handler = get_node_handler()

    area = NodeArea(name="TestArea")
    handler.add_area(area)

    grid = NodeGrid(z=0)
    area.add_grid(grid)

    # Link to same area - no transition should be created
    link = NodeLink(name="north", coord=Coord("TestArea", 0, 1, 0))
    node = Node(coord=Coord("TestArea", 0, 0, 0), links=[link])
    grid.add_node(node)

    # No transition should exist (same area)
    assert len(handler.transitions) == 0

    # Remove link should work without error
    node.remove_link("north")
    assert len(node.links) == 0


def test_get_display_name_no_looker():
    node = Node(coord=Coord("TestArea", 0, 0, 0))
    result = node.get_display_name(looker=None)
    assert result == ""


def test_node_save_snapshot_independence():
    """5.4: save() shallow-copies area refs — mutations during save leak into saved data."""
    import threading
    from unittest.mock import patch
    from atheriz.database_setup import get_database

    handler = NodeHandler()
    area = NodeArea(name="SnapTest")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("SnapTest", 0, 0, 0), desc="original")
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)

    saved_blobs = {}
    real_dumps = dill.dumps
    serialize_event = threading.Event()
    modify_event = threading.Event()

    def slow_dumps(obj, *args, **kwargs):
        if isinstance(obj, NodeArea) and obj.name == "SnapTest":
            serialize_event.set()
            modify_event.wait(timeout=5)
        return real_dumps(obj, *args, **kwargs)

    def mutate_area():
        serialize_event.wait(timeout=5)
        new_node = Node(coord=Coord("SnapTest", 1, 0, 0), desc="injected")
        grid.nodes[(1, 0)] = new_node
        modify_event.set()

    with patch("atheriz.globals.node.dill.dumps", side_effect=slow_dumps):
        t = threading.Thread(target=mutate_area)
        t.start()
        handler.save()
        t.join(timeout=5)

    # read back what was actually persisted
    db = get_database()
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("SELECT data FROM areas WHERE name = ?", ("SnapTest",))
        row = cursor.fetchone()
        assert row is not None, "area was never saved"
        deserialized = dill.loads(row[0])

    assert len(deserialized.grids[0].nodes) == 1, (
        "saved area should reflect pre-mutation state — deep copy snapshot is independent"
    )


def test_save_with_rlock_in_area_data():
    """#46: save() must not fail on values dill can persist (e.g. RLock)."""
    import _thread
    import threading
    from atheriz.database_setup import get_database

    handler = NodeHandler()
    area = NodeArea(name="LockArea")
    area.data["guard"] = threading.RLock()
    handler.add_area(area)

    handler.save()  # should not raise

    db = get_database()
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("SELECT data FROM areas WHERE name = ?", ("LockArea",))
        row = cursor.fetchone()
        assert row is not None, "area was never saved"
        deserialized = dill.loads(row[0])

    lock = deserialized.data["guard"]
    assert isinstance(lock, _thread.RLock)


def test_save_with_unpicklable_data_logs_error():
    """#46: values neither deepcopy nor dill can persist are logged, not fatal."""
    from unittest.mock import patch
    from atheriz.database_setup import get_database

    handler = NodeHandler()
    area = NodeArea(name="BadArea")
    area.data["bad"] = (i for i in range(3))
    handler.add_area(area)

    with patch("atheriz.globals.node.logger.error") as mock_error:
        handler.save()  # should not raise
    mock_error.assert_called_once()

    db = get_database()
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("SELECT data FROM areas WHERE name = ?", ("BadArea",))
        row = cursor.fetchone()
    assert row is None, "unsaveable area must not be persisted"


def test_load_isolates_bad_node_and_per_area_and_updates_max_id():
    """47: per-node and per-area failures during load are isolated and max_id tracks only good nodes."""
    from unittest.mock import patch
    from atheriz.globals import get as get_singleton
    from atheriz.globals.objects import get as get_obj, _ALL_OBJECTS

    class BadDict(dict):
        def values(self):
            raise RuntimeError("injected grid failure")

    handler = NodeHandler()
    handler.clear()
    _ALL_OBJECTS.clear()
    get_singleton.set_id(-1)

    area_good0 = NodeArea(name="Good0")
    grid_good0 = NodeGrid(z=0)
    node_good0 = Node(coord=Coord("Good0", 0, 0, 0))
    grid_good0.nodes[(0, 0)] = node_good0
    area_good0.add_grid(grid_good0)
    handler.add_area(area_good0)

    area_badnode = NodeArea(name="BadNodeArea")
    grid_badnode = NodeGrid(z=0)
    node_bad = Node(coord=Coord("BadNodeArea", 1, 1, 0))
    grid_badnode.nodes[(1, 1)] = node_bad
    area_badnode.add_grid(grid_badnode)
    handler.add_area(area_badnode)

    area_broken = NodeArea(name="BrokenArea")
    grid_broken = NodeGrid(z=0)
    area_broken.add_grid(grid_broken)
    node_broken = Node(coord=Coord("BrokenArea", 0, 0, 0))
    grid_broken.nodes[(0, 0)] = node_broken
    handler.add_area(area_broken)

    area_good1 = NodeArea(name="Good1")
    grid_good1 = NodeGrid(z=0)
    node_good1 = Node(coord=Coord("Good1", 2, 2, 0))
    grid_good1.nodes[(2, 2)] = node_good1
    area_good1.add_grid(grid_good1)
    handler.add_area(area_good1)

    good0_id = node_good0.id
    bad_id = node_bad.id
    good1_id = node_good1.id
    broken_id = node_broken.id
    assert bad_id > good0_id
    handler.save(force=True)
    from atheriz.database_setup import get_database
    import dill

    db = get_database()
    with db.lock:
        cursor = db.connection.cursor()
        cur_area = handler.get_area("BrokenArea")
        cur_grid = cur_area.get_grid(0)
        cur_grid.nodes = BadDict({(0, 0): cur_grid.nodes[(0, 0)]})
        cursor.execute(
            "INSERT OR REPLACE INTO areas (name, data) VALUES (?, ?)",
            (cur_area.name, dill.dumps(cur_area)),
        )
        db.connection.commit()
        cur_grid.nodes = {(0, 0): cur_grid.nodes[(0, 0)]}

    _ALL_OBJECTS.clear()
    get_singleton.set_id(-1)
    orig_resolve = Node.resolve_relations

    def fake_resolve(self):
        if getattr(self.coord, "area", None) == "BadNodeArea":
            raise RuntimeError("injected bad resolve")
        return orig_resolve(self)

    with patch.object(Node, "resolve_relations", fake_resolve):
        with patch("atheriz.globals.node.logger.error") as mock_log:
            handler2 = NodeHandler()
            assert handler2.get_area("Good0") is not None
            assert handler2.get_area("BadNodeArea") is not None
            assert handler2.get_area("BrokenArea") is not None
            assert handler2.get_area("Good1") is not None
            assert get_obj(good0_id)
            assert not get_obj(bad_id)
            assert get_obj(good1_id)
            assert get_singleton.get_id() == max(good0_id, good1_id)
            msgs = " ".join(str(c) for c in mock_log.call_args_list)
            assert "BadNodeArea" in msgs or "Error resolving node" in msgs
            assert "BrokenArea" in msgs or "Error resolving area" in msgs


def test_save_gating_and_force_and_always_save():
    """47: save() gates on _is_dirty unless force or ALWAYS_SAVE_ALL, and clears flags only after COMMIT."""
    from unittest.mock import patch, MagicMock
    from atheriz.globals.objects import _ALL_OBJECTS
    from atheriz.globals import get as get_singleton

    handler = NodeHandler()
    handler.clear()
    _ALL_OBJECTS.clear()
    get_singleton.set_id(-1)

    area = NodeArea(name="GateTest")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("GateTest", 0, 0, 0))
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)

    assert handler._is_dirty() is True
    handler.save(force=True)
    assert handler._is_dirty() is False
    assert handler._modified is False
    assert area.is_modified is False
    with area.lock:
        for g in area.grids.values():
            assert g.is_modified is False
            for n in g.nodes.values():
                with n.lock:
                    assert n.is_modified is False

    with patch("atheriz.globals.node.get_database") as mock_get:
        handler.save(force=False)
        mock_get.assert_not_called()

    with node.lock:
        node.is_modified = True
    assert handler._is_dirty() is True
    handler.save(force=False)
    assert handler._is_dirty() is False

    handler._modified = False
    for a in list(handler.areas.values()):
        a.is_modified = False
        with a.lock:
            for g in list(a.grids.values()):
                g.is_modified = False
                for n in list(g.nodes.values()):
                    try:
                        with n.lock:
                            n.is_modified = False
                    except Exception:
                        pass
    assert handler._is_dirty() is False

    orig_always = settings.ALWAYS_SAVE_ALL
    settings.ALWAYS_SAVE_ALL = True
    try:
        with patch("atheriz.globals.node.get_database") as mock_get:
            mock_db = MagicMock()
            mock_lock = MagicMock()
            mock_lock.__enter__ = MagicMock(return_value=None)
            mock_lock.__exit__ = MagicMock(return_value=False)
            mock_db.lock = mock_lock
            mock_cursor = MagicMock()
            mock_db.connection.cursor.return_value = mock_cursor
            mock_get.return_value = mock_db
            handler.save(force=False)
            mock_get.assert_called()
            assert mock_cursor.execute.called
    finally:
        settings.ALWAYS_SAVE_ALL = orig_always

    for a in list(handler.areas.values()):
        a.is_modified = False
        with a.lock:
            for g in list(a.grids.values()):
                g.is_modified = False
                for n in list(g.nodes.values()):
                    try:
                        with n.lock:
                            n.is_modified = False
                    except Exception:
                        pass
    handler._modified = False
    assert handler._is_dirty() is False
    with patch("atheriz.globals.node.get_database") as mock_get:
        mock_db = MagicMock()
        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=None)
        mock_lock.__exit__ = MagicMock(return_value=False)
        mock_db.lock = mock_lock
        mock_cursor = MagicMock()
        mock_db.connection.cursor.return_value = mock_cursor
        mock_get.return_value = mock_db
        handler.save(force=True)
        mock_get.assert_called()
        assert mock_cursor.execute.called


def test_node_save_post_snapshot_dirty_preserved(global_test_env):
    """2.9: save must not clear a node dirtied after snapshot but before COMMIT."""
    import threading
    from unittest.mock import patch
    from atheriz.utils import detach as orig_detach

    handler = NodeHandler()
    handler.clear()
    area = NodeArea(name="PostSnap")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("PostSnap", 0, 0, 0), desc="orig")
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)
    handler.save(force=True)
    with area.lock:
        area.is_modified = False
    with grid.lock:
        grid.is_modified = False
    with node.lock:
        node.is_modified = False
        node.desc = "clean"
    with handler.lock:
        handler._modified = False
    with node.lock:
        node.is_modified = True
        node.desc = "dirty_before"
    with area.lock:
        area.is_modified = True
    with grid.lock:
        grid.is_modified = True
    with handler.lock:
        handler._modified = True

    barrier_a = threading.Barrier(2, timeout=2)
    barrier_b = threading.Barrier(2, timeout=2)

    def patched(obj):
        is_area = isinstance(obj, NodeArea)
        res = orig_detach(obj)
        if is_area and obj.name == "PostSnap":
            barrier_a.wait(timeout=2)
            barrier_b.wait(timeout=2)
        return res

    def saver():
        with patch("atheriz.globals.node.detach", side_effect=patched):
            handler.save(force=False)

    t = threading.Thread(target=saver)
    t.start()
    barrier_a.wait(timeout=2)
    with node.lock:
        node.desc = "mutated_during_save"
        node.is_modified = True
    barrier_b.wait(timeout=2)
    t.join(timeout=2)
    assert not t.is_alive(), "save deadlocked"
    assert node.is_modified is True, "post-snapshot dirty must not be cleared"
    assert node.desc == "mutated_during_save"
    assert area.is_modified is False, "snapshotted dirty area should be cleared"
    assert grid.is_modified is False


def test_node_save_clean_to_dirty_after_snapshot_preserved(global_test_env):
    """2.9: a clean node dirtied after snapshot must remain dirty."""
    import threading
    from unittest.mock import patch
    from atheriz.utils import detach as orig_detach

    handler = NodeHandler()
    handler.clear()
    area = NodeArea(name="CleanSnap")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("CleanSnap", 0, 0, 0), desc="clean")
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)
    handler.save(force=True)
    with area.lock:
        area.is_modified = False
    with grid.lock:
        grid.is_modified = False
    with node.lock:
        node.is_modified = False
    with handler.lock:
        handler._modified = False
    area2 = NodeArea(name="DirtyOther")
    grid2 = NodeGrid(z=1)
    node2 = Node(coord=Coord("DirtyOther", 0, 0, 1), desc="dirty")
    grid2.nodes[(0, 0)] = node2
    area2.add_grid(grid2)
    handler.add_area(area2)
    with area2.lock:
        area2.is_modified = True
    with grid2.lock:
        grid2.is_modified = True
    with node2.lock:
        node2.is_modified = True
    with handler.lock:
        handler._modified = True
    assert node.is_modified is False
    assert node2.is_modified is True

    barrier_a = threading.Barrier(2, timeout=2)
    barrier_b = threading.Barrier(2, timeout=2)
    count = [0]

    def patched(obj):
        is_area = isinstance(obj, NodeArea)
        res = orig_detach(obj)
        if is_area:
            count[0] += 1
            if count[0] == 1 and obj.name == "CleanSnap":
                barrier_a.wait(timeout=2)
                barrier_b.wait(timeout=2)
        return res

    def saver():
        with patch("atheriz.globals.node.detach", side_effect=patched):
            handler.save(force=False)

    t = threading.Thread(target=saver)
    t.start()
    barrier_a.wait(timeout=2)
    with node.lock:
        node.desc = "mutated_clean"
        node.is_modified = True
    barrier_b.wait(timeout=2)
    t.join(timeout=2)
    assert not t.is_alive()
    assert node.is_modified is True, "clean->dirty after snapshot must stay dirty"
    assert node2.is_modified is False, "dirty at snapshot must be cleared"


def test_node_save_clears_only_snapshotted(global_test_env):
    """2.9: new area/grid/node added after snapshot must not be cleared."""
    import threading
    from unittest.mock import patch
    from atheriz.utils import detach as orig_detach

    handler = NodeHandler()
    handler.clear()
    area = NodeArea(name="SnapOnly")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("SnapOnly", 0, 0, 0), desc="orig")
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)
    handler.save(force=True)
    with area.lock:
        area.is_modified = False
    with grid.lock:
        grid.is_modified = False
    with node.lock:
        node.is_modified = False
    with handler.lock:
        handler._modified = False
    with area.lock:
        area.is_modified = True
    with grid.lock:
        grid.is_modified = True
    with node.lock:
        node.is_modified = True
    with handler.lock:
        handler._modified = True

    barrier_a = threading.Barrier(2, timeout=2)
    barrier_b = threading.Barrier(2, timeout=2)

    def patched(obj):
        is_area = isinstance(obj, NodeArea) and obj.name == "SnapOnly"
        res = orig_detach(obj)
        if is_area:
            barrier_a.wait(timeout=2)
            barrier_b.wait(timeout=2)
        return res

    def saver():
        with patch("atheriz.globals.node.detach", side_effect=patched):
            handler.save(force=False)

    t = threading.Thread(target=saver)
    t.start()
    barrier_a.wait(timeout=2)
    new_area = NodeArea(name="NewAfterSnap")
    new_grid = NodeGrid(z=1)
    new_node = Node(coord=Coord("NewAfterSnap", 0, 0, 1), desc="new")
    new_grid.nodes[(0, 0)] = new_node
    new_area.add_grid(new_grid)
    handler.add_area(new_area)
    assert new_node.is_modified is True
    assert new_area.is_modified is True
    barrier_b.wait(timeout=2)
    t.join(timeout=2)
    assert not t.is_alive()
    assert new_node.is_modified is True, "new node added after snapshot must not be cleared"
    assert new_area.is_modified is True
    with new_grid.lock:
        assert new_grid.is_modified is True
    assert node.is_modified is False


def test_node_save_rollback_restores_dirty(global_test_env):
    """2.9: ROLLBACK must restore dirty flags cleared at snapshot."""
    from unittest.mock import patch, MagicMock

    handler = NodeHandler()
    handler.clear()
    area = NodeArea(name="RollbackArea")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("RollbackArea", 0, 0, 0), desc="orig")
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)
    with area.lock:
        area.is_modified = True
    with grid.lock:
        grid.is_modified = True
    with node.lock:
        node.is_modified = True
    with handler.lock:
        handler._modified = True

    mock_db = MagicMock()
    mock_lock = MagicMock()
    mock_lock.__enter__ = MagicMock(return_value=None)
    mock_lock.__exit__ = MagicMock(return_value=False)
    mock_db.lock = mock_lock
    mock_cursor = MagicMock()

    def _exec(sql, params=()):
        if "COMMIT" in sql:
            raise RuntimeError("injected COMMIT failure")
        return None

    mock_cursor.execute.side_effect = _exec
    mock_db.connection.cursor.return_value = mock_cursor
    mock_db._closed = False

    with patch("atheriz.globals.node.get_database", return_value=mock_db):
        handler.save(force=False)

    assert handler._modified is True, "handler flag must be restored on ROLLBACK"
    assert area.is_modified is True
    with grid.lock:
        assert grid.is_modified is True
    with node.lock:
        assert node.is_modified is True


def test_node_save_db_closed_restores_dirty(global_test_env):
    """2.9: early return on closed DB must restore dirty flags."""
    from unittest.mock import patch, MagicMock

    handler = NodeHandler()
    handler.clear()
    area = NodeArea(name="ClosedArea")
    grid = NodeGrid(z=0)
    node = Node(coord=Coord("ClosedArea", 0, 0, 0), desc="orig")
    grid.nodes[(0, 0)] = node
    area.add_grid(grid)
    handler.add_area(area)
    with area.lock:
        area.is_modified = True
    with grid.lock:
        grid.is_modified = True
    with node.lock:
        node.is_modified = True
    with handler.lock:
        handler._modified = True

    mock_db = MagicMock()
    mock_lock = MagicMock()
    mock_lock.__enter__ = MagicMock(return_value=None)
    mock_lock.__exit__ = MagicMock(return_value=False)
    mock_db.lock = mock_lock
    mock_db._closed = True

    with patch("atheriz.globals.node.get_database", return_value=mock_db):
        handler.save(force=False)

    assert handler._modified is True
    assert area.is_modified is True
    with grid.lock:
        assert grid.is_modified is True
    with node.lock:
        assert node.is_modified is True
