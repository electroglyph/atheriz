import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.utils import Coord
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.objects.base_door import Door
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import get
from atheriz import settings


def _make_node_pair(area="TestArea", x1=0, y1=0, x2=0, y2=1, z=0):
    nh = get_node_handler()
    area_obj = NodeArea(name=area)
    grid = NodeGrid(z=z)
    node1 = Node(coord=Coord(area, x1, y1, z))
    node2 = Node(coord=Coord(area, x2, y2, z))
    node1.add_link(NodeLink(name="north", coord=Coord(area, x2, y2, z)))
    node2.add_link(NodeLink(name="south", coord=Coord(area, x1, y1, z)))
    grid.add_node(node1)
    grid.add_node(node2)
    area_obj.add_grid(grid)
    nh.add_area(area_obj)
    return node1, node2, nh


def _setup_two_nodes_with_door(closed=True):
    nh = get_node_handler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    node1 = Node(coord=Coord("TestArea", 0, 0, 0))
    node2 = Node(coord=Coord("TestArea", 0, 2, 0))
    node1.add_link(NodeLink(name="north", coord=Coord("TestArea", 0, 2, 0)))
    node2.add_link(NodeLink(name="south", coord=Coord("TestArea", 0, 0, 0)))
    grid.add_node(node1)
    grid.add_node(node2)
    area.add_grid(grid)
    nh.add_area(area)
    door = Door.create(
        from_coord=Coord("TestArea", 0, 0, 0),
        from_exit="north",
        to_coord=Coord("TestArea", 0, 2, 0),
        to_exit="south",
        symbol_coord=(0, 1),
        closed_symbol="X",
        open_symbol="O",
        closed=closed,
    )
    mock_mh = MagicMock()
    mock_mi = MagicMock()
    mock_mi.lock = MagicMock()
    mock_mi.lock.__enter__ = MagicMock(return_value=None)
    mock_mi.lock.__exit__ = MagicMock(return_value=False)
    mock_mi.post_grid = {}
    mock_mi.pre_grid = {}
    mock_mi.map_changed = False
    mock_mi.render = MagicMock()
    mock_mh.get_mapinfo.return_value = mock_mi
    with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
         patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh):
        nh.add_door(door)
    return node1, node2, door, nh, mock_mh


class TestDoorStaysClosedWhenMoveFails:
    def test_door_remains_closed_and_map_reverted_when_move_fails_after_open(self):
        node1, node2, door, nh, mock_mh = _setup_two_nodes_with_door(closed=True)
        assert door.closed is True
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh), \
             patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            with patch.object(node2, "at_pre_object_receive", return_value=False):
                with patch.object(door, "map_close", wraps=door.map_close) as mock_map_close, \
                     patch.object(door, "try_close", wraps=door.try_close) as mock_try_close:
                    ex = ExitCommand()
                    ex.caller_id = caller.id
                    ex.location = node1.coord
                    ex.destination = node2.coord
                    ex.name = "north"
                    ex.do_move()
                    assert door.closed is True
                    assert caller.location is node1
                    assert caller.location != node2
                    assert mock_try_close.called or mock_map_close.called

    def test_door_closes_after_successful_move(self):
        node1, node2, door, nh, mock_mh = _setup_two_nodes_with_door(closed=True)
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh), \
             patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            ex = ExitCommand()
            ex.caller_id = caller.id
            ex.location = node1.coord
            ex.destination = node2.coord
            ex.name = "north"
            ex.do_move()
            assert caller.location == node2
            assert door.closed is True

    def test_open_door_branch_does_not_revert_on_move_failure(self):
        node1, node2, door, nh, mock_mh = _setup_two_nodes_with_door(closed=False)
        assert door.closed is False
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh), \
             patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            with patch.object(node2, "at_pre_object_receive", return_value=False):
                with patch.object(door, "map_close") as mock_close, \
                     patch.object(door, "try_close") as mock_try_close:
                    ex = ExitCommand()
                    ex.caller_id = caller.id
                    ex.location = node1.coord
                    ex.destination = node2.coord
                    ex.name = "north"
                    ex.do_move()
                    assert door.closed is False
                    assert caller.location == node1
                    mock_try_close.assert_not_called()
                    mock_close.assert_not_called()

    def test_open_door_branch_does_not_revert_on_success(self):
        node1, node2, door, nh, mock_mh = _setup_two_nodes_with_door(closed=False)
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh), \
             patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            initial_closed = door.closed
            ex = ExitCommand()
            ex.caller_id = caller.id
            ex.location = node1.coord
            ex.destination = node2.coord
            ex.name = "north"
            ex.do_move()
            assert door.closed == initial_closed
            assert door.closed is False
            assert caller.location == node2

    def test_door_try_close_fallback_ensures_closed_when_try_close_denied(self):
        node1, node2, door, nh, mock_mh = _setup_two_nodes_with_door(closed=True)
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh), \
             patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            with patch.object(node2, "at_pre_object_receive", return_value=False):
                with patch.object(door, "try_close", return_value=False) as mock_try:
                    ex = ExitCommand()
                    ex.caller_id = caller.id
                    ex.location = node1.coord
                    ex.destination = node2.coord
                    ex.name = "north"
                    ex.do_move()
                    assert door.closed is True
                    mock_try.assert_called()

    def test_door_exception_during_move_reverts_to_closed(self):
        node1, node2, door, nh, mock_mh = _setup_two_nodes_with_door(closed=True)
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        with patch("atheriz.globals.node.get_map_handler", return_value=mock_mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mock_mh), \
             patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            with patch.object(caller, "move_to", side_effect=RuntimeError("boom")):
                ex = ExitCommand()
                ex.caller_id = caller.id
                ex.location = node1.coord
                ex.destination = node2.coord
                ex.name = "north"
                try:
                    ex.do_move()
                    assert False, "should have raised"
                except RuntimeError:
                    pass
                assert door.closed is True

    def test_move_without_door_unaffected(self):
        node1, node2, nh = _make_node_pair()
        caller = Object.create(None, "Hero", is_pc=True)
        caller.is_connected = True
        caller.location = node1
        node1.add_object(caller)
        caller.msg = MagicMock()
        nh.doors.clear()
        with patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh):
            ex = ExitCommand()
            ex.caller_id = caller.id
            ex.location = node1.coord
            ex.destination = node2.coord
            ex.name = "north"
            ex.do_move()
            assert caller.location == node2
