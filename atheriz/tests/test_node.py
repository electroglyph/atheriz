import pytest
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink, Door, Transition
from atheriz.singletons.node import NodeHandler
from atheriz.singletons import objects as obj_singleton
from atheriz import settings
from pathlib import Path
import shutil




# ==================== NodeLink Tests ====================


def test_nodelink_init():
    link = NodeLink(name="north", coord=("TestArea", 0, 1, 0), aliases=["n"])
    assert link.name == "north"
    assert link.coord == ("TestArea", 0, 1, 0)
    assert link.aliases == ["n"]


def test_nodelink_str():
    link = NodeLink(name="south", coord=("TestArea", 0, 0, 0))
    s = str(link)
    assert "south" in s
    assert "TestArea" in s


# ==================== Node Tests ====================


def test_node_init():
    node = Node(coord=("TestArea", 1, 2, 3), desc="A dark room")
    assert node.coord == ("TestArea", 1, 2, 3)
    assert node.desc == "A dark room"
    assert node.links is None  # defaults to None, not []


def test_node_with_links():
    link = NodeLink(name="north", coord=("TestArea", 0, 1, 0))
    node = Node(coord=("TestArea", 0, 0, 0), links=[link])
    assert len(node.links) == 1
    assert node.links[0].name == "north"


def test_node_add_link():
    node = Node(coord=("TestArea", 0, 0, 0))
    link = NodeLink(name="east", coord=("TestArea", 1, 0, 0))
    node.add_link(link)
    assert len(node.links) == 1
    assert node.links[0].name == "east"


# Note: Node class doesn't have get_link or remove_link that work standalone
# remove_link tries to remove transitions which requires proper setup


def test_node_data():
    node = Node(coord=("TestArea", 0, 0, 0))
    node.set_data("key1", "value1")
    assert node.get_data("key1") == "value1"
    assert node.get_data("nonexistent") is None
    node.remove_data("key1")
    assert node.get_data("key1") is None


def test_node_nouns():
    node = Node(coord=("TestArea", 0, 0, 0))
    node.add_noun("fountain", "A marble fountain with clear water")
    assert node.get_noun("fountain") == "A marble fountain with clear water"
    node.remove_noun("fountain")
    assert node.get_noun("fountain") is None


def test_node_equality():
    node1 = Node(coord=("TestArea", 0, 0, 0))
    node2 = Node(coord=("TestArea", 0, 0, 0))
    node3 = Node(coord=("TestArea", 1, 0, 0))

    assert node1 == node2
    assert node1 != node3


# ==================== NodeGrid Tests ====================


def test_nodegrid_init():
    grid = NodeGrid(z=5)
    assert grid.z == 5
    assert len(grid) == 0


def test_nodegrid_add_get_node():
    grid = NodeGrid(z=0)
    node = Node(coord=("TestArea", 1, 2, 0))
    grid.nodes[(1, 2)] = node

    assert len(grid) == 1
    assert grid.get_node((1, 2)) == node
    assert grid.get_node((0, 0)) is None


def test_nodegrid_clear():
    grid = NodeGrid(z=0)
    grid.nodes[(0, 0)] = Node(coord=("TestArea", 0, 0, 0))
    grid.nodes[(1, 1)] = Node(coord=("TestArea", 1, 1, 0))
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
    node1 = Node(coord=("TestArea", 0, 0, 0))
    node2 = Node(coord=("TestArea", 1, 1, 0))
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
        from_coord=("Area1", 0, 0, 0), to_coord=("Area2", 0, 0, 0), from_link="north"
    )
    assert trans.from_coord == ("Area1", 0, 0, 0)
    assert trans.to_coord == ("Area2", 0, 0, 0)
    assert trans.from_link == "north"


# ==================== Door Tests ====================


def test_door_init():
    door = Door(
        from_coord=("Area1", 0, 0, 0),
        to_coord=("Area2", 0, 0, 0),
        from_exit="north",
        to_exit="south",
    )
    assert door.from_coord == ("Area1", 0, 0, 0)
    assert door.to_coord == ("Area2", 0, 0, 0)
    assert door.from_exit == "north"
    assert door.to_exit == "south"
    assert door.closed.test() is True  # default closed
    assert door.locked.test() is False  # default unlocked


def test_door_open_close():
    door = Door(from_coord=("A", 0, 0, 0), to_coord=("B", 0, 0, 0), from_exit="n", to_exit="s")

    assert door.closed.test() is True
    door.closed.clear()  # open
    assert door.closed.test() is False
    door.closed.test_and_set()  # close (sets flag and returns previous value)
    assert door.closed.test() is True


def test_door_lock_unlock():
    door = Door(
        from_coord=("A", 0, 0, 0), to_coord=("B", 0, 0, 0), from_exit="n", to_exit="s", locked=True
    )

    assert door.locked.test() is True
    door.locked.clear()  # unlock
    assert door.locked.test() is False
    door.locked.test_and_set()  # lock
    assert door.locked.test() is True


def test_door_desc():
    door = Door(
        from_coord=("Area1", 0, 0, 0),
        to_coord=("Area2", 0, 0, 0),
        from_exit="north",
        to_exit="south",
    )

    desc_from = door.desc(("Area1", 0, 0, 0))
    assert "north" in desc_from
    assert "closed" in desc_from.lower()

    door.closed.clear()  # open
    desc_open = door.desc(("Area1", 0, 0, 0))
    assert "open" in desc_open.lower()


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
    node = Node(coord=("TestArea", 5, 10, 0))
    grid.nodes[(5, 10)] = node
    area.add_grid(grid)
    handler.add_area(area)

    result = handler.get_node(("TestArea", 5, 10, 0))
    assert result == node

    assert handler.get_node(("TestArea", 99, 99, 0)) is None
    assert handler.get_node(("NonexistentArea", 0, 0, 0)) is None


def test_nodehandler_get_nodes():
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    node1 = Node(coord=("TestArea", 0, 0, 0))
    node2 = Node(coord=("TestArea", 1, 1, 0))
    grid.nodes[(0, 0)] = node1
    grid.nodes[(1, 1)] = node2
    area.add_grid(grid)
    handler.add_area(area)

    nodes = handler.get_nodes([("TestArea", 0, 0, 0), ("TestArea", 1, 1, 0)])
    assert len(nodes) == 2


def test_nodehandler_add_remove_transition():
    handler = NodeHandler()
    trans = Transition(
        from_coord=("Area1", 0, 0, 0), to_coord=("Area2", 0, 0, 0), from_link="north"
    )

    handler.add_transition(trans)
    assert ("Area2", 0, 0, 0) in handler.transitions

    handler.remove_transition(("Area2", 0, 0, 0))
    assert ("Area2", 0, 0, 0) not in handler.transitions


def test_nodehandler_find_transitions():
    handler = NodeHandler()

    t1 = Transition(from_coord=("Area1", 0, 0, 0), to_coord=("Area2", 0, 0, 0), from_link="north")
    t2 = Transition(from_coord=("Area1", 0, 0, 1), to_coord=("Area3", 0, 0, 1), from_link="up")
    t3 = Transition(from_coord=("Area2", 0, 0, 0), to_coord=("Area1", 0, 0, 0), from_link="south")

    handler.add_transition(t1)
    handler.add_transition(t2)
    handler.add_transition(t3)

    # Find by from_area
    results = handler.find_transitions(from_area="Area1")
    assert len(results) == 2

    # Find by to_area
    results = handler.find_transitions(to_area="Area2")
    assert len(results) == 1


def test_nodehandler_add_door():
    handler = NodeHandler()
    door = Door(
        from_coord=("Area1", 0, 0, 0),
        to_coord=("Area2", 0, 0, 0),
        from_exit="north",
        to_exit="south",
    )

    handler.add_door(door)

    # Door should be accessible from both sides
    doors_from = handler.get_doors(("Area1", 0, 0, 0))
    doors_to = handler.get_doors(("Area2", 0, 0, 0))

    assert "north" in doors_from
    assert "south" in doors_to
    assert doors_from["north"] == door
    assert doors_to["south"] == door


# ==================== Integration Tests ====================
# These tests require full area/grid/handler setup


def test_nodegrid_add_node_creates_transition():
    """Adding a node with a link to another area should create a transition"""
    from atheriz.singletons.get import get_node_handler

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
    link = NodeLink(name="north", coord=("Area2", 0, 0, 0))
    node = Node(coord=("Area1", 0, 0, 0), links=[link])

    # Add node via grid - this should create a transition
    grid.add_node(node)

    # Verify transition was created
    assert ("Area2", 0, 0, 0) in handler.transitions
    trans = handler.transitions[("Area2", 0, 0, 0)]
    assert trans.from_coord == ("Area1", 0, 0, 0)
    assert trans.from_link == "north"


def test_nodegrid_remove_node_removes_transition():
    """Removing a node with a cross-area link should remove the transition"""
    from atheriz.singletons.get import get_node_handler

    handler = get_node_handler()

    # Setup areas
    area1 = NodeArea(name="Area1")
    area2 = NodeArea(name="Area2")
    handler.add_area(area1)
    handler.add_area(area2)

    grid = NodeGrid(z=0)
    area1.add_grid(grid)

    link = NodeLink(name="north", coord=("Area2", 0, 0, 0))
    node = Node(coord=("Area1", 0, 0, 0), links=[link])
    grid.add_node(node)

    # Verify transition exists
    assert ("Area2", 0, 0, 0) in handler.transitions

    # Remove the node
    grid.remove_node((0, 0))

    # Verify transition was removed
    assert ("Area2", 0, 0, 0) not in handler.transitions


def test_node_remove_link_removes_transition():
    """Removing a cross-area link from a node should remove the transition"""
    from atheriz.singletons.get import get_node_handler

    handler = get_node_handler()

    # Setup areas
    area1 = NodeArea(name="Area1")
    area2 = NodeArea(name="Area2")
    handler.add_area(area1)
    handler.add_area(area2)

    grid = NodeGrid(z=0)
    area1.add_grid(grid)

    link = NodeLink(name="north", coord=("Area2", 0, 0, 0))
    node = Node(coord=("Area1", 0, 0, 0), links=[link])
    grid.add_node(node)

    # Verify transition exists
    assert ("Area2", 0, 0, 0) in handler.transitions

    # Remove the link from the node
    node.remove_link("north")

    # Verify transition was removed
    assert ("Area2", 0, 0, 0) not in handler.transitions
    assert len(node.links) == 0


def test_node_remove_link_same_area_no_transition():
    """Removing a same-area link should not try to remove transitions"""
    from atheriz.singletons.get import get_node_handler

    handler = get_node_handler()

    area = NodeArea(name="TestArea")
    handler.add_area(area)

    grid = NodeGrid(z=0)
    area.add_grid(grid)

    # Link to same area - no transition should be created
    link = NodeLink(name="north", coord=("TestArea", 0, 1, 0))
    node = Node(coord=("TestArea", 0, 0, 0), links=[link])
    grid.add_node(node)

    # No transition should exist (same area)
    assert len(handler.transitions) == 0

    # Remove link should work without error
    node.remove_link("north")
    assert len(node.links) == 0
