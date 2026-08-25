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

class TestDoorLockAndPathfind:

    def test_door_try_lock_open_fails_not_locked(self, global_test_env):
        nh = NodeHandler()
        door = Door.create(
            from_coord=Coord("A", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("A", 0, 1, 0),
            to_exit="south",
            closed=False,
            locked=False,
        )
        caller = MagicMock()
        caller.is_builder = True
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        door.access = MagicMock(return_value=True)
        result = door.try_lock(caller)
        assert result is False
        assert door.locked is False

    def test_door_try_lock_open_fails_even_if_access_true(self, global_test_env):
        door = Door.create(
            from_coord=Coord("A", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("A", 0, 1, 0),
            to_exit="south",
            closed=False,
            locked=False,
        )
        caller = MagicMock()
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        door.access = MagicMock(return_value=True)
        assert door.try_lock(caller) is False
        assert door.locked is False
        door2 = Door.create(
            from_coord=Coord("B", 0, 0, 0),
            from_exit="east",
            to_coord=Coord("B", 1, 0, 0),
            to_exit="west",
            closed=False,
            locked=False,
        )
        door2.access = MagicMock(return_value=True)
        assert door2.try_lock(MagicMock(location=MagicMock(msg_contents=MagicMock()))) is False

    def test_door_try_lock_closed_succeeds(self, global_test_env):
        door = Door.create(
            from_coord=Coord("A", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("A", 0, 1, 0),
            to_exit="south",
            closed=True,
            locked=False,
        )
        caller = MagicMock()
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        door.access = MagicMock(return_value=True)
        result = door.try_lock(caller)
        assert result is True
        assert door.locked is True

    def test_door_try_lock_closed_already_locked_fails(self, global_test_env):
        door = Door.create(
            from_coord=Coord("A", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("A", 0, 1, 0),
            to_exit="south",
            closed=True,
            locked=True,
        )
        caller = MagicMock()
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        door.access = MagicMock(return_value=True)
        result = door.try_lock(caller)
        assert result is False
        assert door.locked is True

    def test_door_try_lock_no_access_fails(self, global_test_env):
        door = Door.create(
            from_coord=Coord("A", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("A", 0, 1, 0),
            to_exit="south",
            closed=True,
            locked=False,
        )
        caller = MagicMock()
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        door.access = MagicMock(return_value=False)
        result = door.try_lock(caller)
        assert result is False
        assert door.locked is False

    def _setup_pathfind_two_nodes(self, door_closed, door_locked, access_mock=None):
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name="PathArea")
        grid = NodeGrid(area="PathArea", z=0)
        n1 = Node(coord=Coord("PathArea", 0, 0, 0))
        n2 = Node(coord=Coord("PathArea", 1, 0, 0))
        n1.add_link(NodeLink("east", Coord("PathArea", 1, 0, 0), ["e"]))
        n2.add_link(NodeLink("west", Coord("PathArea", 0, 0, 0), ["w"]))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)
        door = Door.create(
            from_coord=Coord("PathArea", 0, 0, 0),
            from_exit="east",
            to_coord=Coord("PathArea", 1, 0, 0),
            to_exit="west",
            closed=door_closed,
            locked=door_locked,
        )
        if access_mock is not None:
            door.access = access_mock
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)
        return nh, n1, n2, door, mh

    def test_pathfind_open_locked_still_traversable(self, global_test_env):
        def access_mock(caller, perm):
            return False
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=False, door_locked=True, access_mock=MagicMock(side_effect=access_mock))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is True
        assert len(path) == 2
        assert path[0] == n1
        assert path[1] == n2

    def test_pathfind_closed_locked_without_unlock_blocks(self, global_test_env):
        def access_mock(caller, perm):
            if perm == "unlock":
                return False
            if perm == "open":
                return True
            return True
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=True, door_locked=True, access_mock=MagicMock(side_effect=access_mock))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is False
        assert path == []

    def test_pathfind_closed_locked_with_unlock_allows(self, global_test_env):
        def access_mock(caller, perm):
            return True
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=True, door_locked=True, access_mock=MagicMock(side_effect=access_mock))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is True
        assert len(path) == 2
        assert path[1] == n2

    def test_pathfind_closed_without_open_blocks(self, global_test_env):
        def access_mock(caller, perm):
            if perm == "open":
                return False
            return True
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=True, door_locked=False, access_mock=MagicMock(side_effect=access_mock))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is False

    def test_pathfind_closed_with_open_allows(self, global_test_env):
        def access_mock(caller, perm):
            if perm == "open":
                return True
            return True
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=True, door_locked=False, access_mock=MagicMock(side_effect=access_mock))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is True
        assert len(path) == 2

    def test_pathfind_open_locked_with_unlock_and_open_true_still_traversable(self, global_test_env):
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=False, door_locked=True, access_mock=MagicMock(return_value=True))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is True

    def test_exit_command_open_locked_allows_move_legacy(self, global_test_env):
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name="ExitArea")
        grid = NodeGrid(area="ExitArea", z=0)
        src = Node(coord=Coord("ExitArea", 0, 0, 0))
        dst = Node(coord=Coord("ExitArea", 0, 1, 0))
        src.add_link(NodeLink("north", Coord("ExitArea", 0, 1, 0), ["n"]))
        dst.add_link(NodeLink("south", Coord("ExitArea", 0, 0, 0), ["s"]))
        grid.add_node(src)
        grid.add_node(dst)
        area.add_grid(grid)
        nh.add_area(area)
        door = Door.create(
            from_coord=Coord("ExitArea", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("ExitArea", 0, 1, 0),
            to_exit="south",
            closed=False,
            locked=True,
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)

        player = Object.create(None, "Hero", is_pc=True)
        player.location = src
        src.add_object(player)
        player.msg = MagicMock()

        cmd = ExitCommand()
        cmd.caller_id = player.id
        cmd.location = src.coord
        cmd.destination = dst.coord
        cmd.name = "north"
        cmd.key = "north"

        with patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh), \
             patch("atheriz.objects.base_obj.get_node_handler", return_value=nh), \
             patch("atheriz.globals.get.get_node_handler", return_value=nh), \
             patch("atheriz.settings.MAP_ENABLED", False):
            cmd.do_move()

        assert player.location == dst

    def test_exit_command_closed_locked_blocks_without_try_open(self, global_test_env):
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name="ExitArea2")
        grid = NodeGrid(area="ExitArea2", z=0)
        src = Node(coord=Coord("ExitArea2", 0, 0, 0))
        dst = Node(coord=Coord("ExitArea2", 0, 1, 0))
        src.add_link(NodeLink("north", Coord("ExitArea2", 0, 1, 0), ["n"]))
        dst.add_link(NodeLink("south", Coord("ExitArea2", 0, 0, 0), ["s"]))
        grid.add_node(src)
        grid.add_node(dst)
        area.add_grid(grid)
        nh.add_area(area)
        door = Door.create(
            from_coord=Coord("ExitArea2", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("ExitArea2", 0, 1, 0),
            to_exit="south",
            closed=True,
            locked=True,
        )
        door.access = MagicMock(return_value=False)
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)

        player = Object.create(None, "Hero2", is_pc=True)
        player.location = src
        src.add_object(player)
        player.msg = MagicMock()

        cmd = ExitCommand()
        cmd.caller_id = player.id
        cmd.location = src.coord
        cmd.destination = dst.coord
        cmd.name = "north"
        cmd.key = "north"

        with patch("atheriz.commands.loggedin.exit.get_node_handler", return_value=nh), \
             patch("atheriz.settings.MAP_ENABLED", False):
            cmd.do_move()

        assert player.location == src
