import pytest
from unittest.mock import MagicMock, patch, call
from atheriz.utils import Coord
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_door import Door
from atheriz.objects.base_obj import Object
from atheriz.pathfind import astar
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz import settings


class MockMapInfo:
    def __init__(self):
        self.lock = MagicMock()
        self.lock.__enter__ = MagicMock(return_value=None)
        self.lock.__exit__ = MagicMock(return_value=False)
        self.post_grid = {}
        self.pre_grid = None
        self.map_changed = False
    def update_grid(self, coord, symbol):
        pass
    def render(self, force=False):
        pass

class MockMapHandler:
    def get_mapinfo(self, area, z):
        return MockMapInfo()

def _patch_map_handler():
    return patch("atheriz.globals.node.get_map_handler", return_value=MockMapHandler())

def _patch_all_node_handlers(nh):
    return patch.multiple(
        "atheriz.globals.get",
        get_node_handler=MagicMock(return_value=nh),
    )

def make_two_nodes(area="TestArea", z=0):
    n1 = Node(coord=Coord(area, 0, 0, z))
    n2 = Node(coord=Coord(area, 0, 1, z))
    with n1.lock:
        n1.links = []
        n1._contents = set()
    with n2.lock:
        n2.links = []
        n2._contents = set()
    return n1, n2

def make_handler_with_two_nodes(area_name="TestArea", z=0):
    nh = NodeHandler()
    area = NodeArea(name=area_name)
    grid = NodeGrid(area=area_name, z=z)
    n1 = Node(coord=Coord(area_name, 0, 0, z))
    n2 = Node(coord=Coord(area_name, 0, 1, z))
    n1.add_link(NodeLink("north", Coord(area_name, 0, 1, z), ["n"]))
    n2.add_link(NodeLink("south", Coord(area_name, 0, 0, z), ["s"]))
    grid.add_node(n1)
    grid.add_node(n2)
    area.add_grid(grid)
    nh.add_area(area)
    return nh, n1, n2, area, grid

class TestMoveHooksTransactional:

    def test_move_hooks_node_dest_pre_fails_does_not_trigger_leave(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), False)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        mover = Object.create(None, "Mover", is_pc=True)
        mover.location = n1
        n1.add_object(mover)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = mover.move_to(n2, to_exit="north", announce=False)

        assert ok is False
        assert calls == ["pre_leave", "pre_receive"]
        n1.at_object_leave.assert_not_called()
        n2.at_object_receive.assert_not_called()
        assert mover.location == n1
        assert mover.id in n1._contents
        assert mover.id not in n2._contents
        assert n1.at_pre_object_leave.called
        assert n2.at_pre_object_receive.called

    def test_move_hooks_node_success_order_is_transactional(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), True)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        mover = Object.create(None, "Mover2", is_pc=True)
        mover.location = n1
        n1.add_object(mover)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = mover.move_to(n2, to_exit="north", announce=False)

        assert ok is True
        assert calls == ["pre_leave", "pre_receive", "leave", "receive"]
        assert mover.location == n2
        assert mover.id not in n1._contents
        assert mover.id in n2._contents

    def test_move_hooks_node_source_pre_fails_no_dest_pre(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), False)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), True)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        mover = Object.create(None, "Mover3", is_pc=True)
        mover.location = n1
        n1.add_object(mover)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = mover.move_to(n2, to_exit="north", announce=False)

        assert ok is False
        assert calls == ["pre_leave"]
        n2.at_pre_object_receive.assert_not_called()
        n1.at_object_leave.assert_not_called()
        n2.at_object_receive.assert_not_called()
        assert mover.location == n1
        assert mover.id in n1._contents

    def test_move_hooks_node_success_contents_swap(self, global_test_env):
        n1, n2 = make_two_nodes()
        mover = Object.create(None, "Mover4", is_pc=True)
        mover.location = n1
        n1.add_object(mover)
        assert mover.id in n1._contents
        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = mover.move_to(n2, announce=False)
        assert ok is True
        assert mover.location == n2
        assert mover.id not in n1._contents
        assert mover.id in n2._contents

    def test_move_hooks_item_node_dest_pre_fails(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), False)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        item = Object.create(None, "Apple", is_item=True)
        item.location = n1
        n1.add_object(item)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item.move_to(n2, announce=False)

        assert ok is False
        assert calls == ["pre_leave", "pre_receive"]
        assert item.location == n1
        assert item.id in n1._contents
        assert item.id not in n2._contents

    def test_move_hooks_item_node_success_order(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), True)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        item = Object.create(None, "Gem", is_item=True)
        item.location = n1
        n1.add_object(item)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item.move_to(n2, announce=False)

        assert ok is True
        assert calls == ["pre_leave", "pre_receive", "leave", "receive"]
        assert item.location == n2
        assert item.id not in n1._contents
        assert item.id in n2._contents

    def test_move_hooks_item_container_dest_pre_fails_similar(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), False)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        container = Object.create(None, "Chest", is_item=True, is_container=True)
        container_calls = []
        container.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (container_calls.append("pre_leave"), True)[1])
        container.at_object_leave = MagicMock(side_effect=lambda *a, **k: container_calls.append("leave"))

        item2 = Object.create(None, "Coin", is_item=True)
        item2.location = container
        container.add_object(item2)

        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (container_calls.append("pre_receive"), False)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: container_calls.append("receive"))

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item2.move_to(n2, announce=False)

        assert ok is False
        assert item2.location == container
        assert item2.id in container._contents
        assert item2.id not in n2._contents
        assert "receive" not in container_calls

    def test_move_hooks_item_container_success_order_similar(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), True)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        item = Object.create(None, "Potion", is_item=True, is_container=True)
        item.location = n1
        n1.add_object(item)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item.move_to(n2, announce=False)

        assert ok is True
        assert calls == ["pre_leave", "pre_receive", "leave", "receive"]
        assert item.location == n2
