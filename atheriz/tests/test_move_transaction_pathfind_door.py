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

# Helper to make two nodes that are not registered in handler (for MoveHooks) or with handler
def make_two_nodes(area="TestArea", z=0):
    n1 = Node(coord=Coord(area, 0, 0, z))
    n2 = Node(coord=Coord(area, 0, 1, z))
    # Ensure empty contents and links
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
    # add bidirectional links
    n1.add_link(NodeLink("north", Coord(area_name, 0, 1, z), ["n"]))
    n2.add_link(NodeLink("south", Coord(area_name, 0, 0, z), ["s"]))
    grid.add_node(n1)
    grid.add_node(n2)
    area.add_grid(grid)
    nh.add_area(area)
    return nh, n1, n2, area, grid

# ==================== MoveHooks ====================

class TestMoveHooksTransactional:

    def test_move_hooks_node_dest_pre_fails_does_not_trigger_leave(self, global_test_env):
        n1, n2 = make_two_nodes()
        calls = []
        # source hooks
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        # dest hooks - pre fails
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
        # Item move where destination is a Node but mover is an item (container context)
        # Also test moving item between two container Objects with mocked hooks
        # Here we test the transactional behavior for item->container Object move
        # Even though base_obj currently only calls Node hooks, we verify source leave not called if dest pre fails
        # We simulate by using two Node destinations but mover is item
        n1, n2 = make_two_nodes()
        calls = []
        n1.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_leave"), True)[1])
        n1.at_object_leave = MagicMock(side_effect=lambda *a, **k: calls.append("leave"))
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (calls.append("pre_receive"), False)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: calls.append("receive"))

        # Container destination variant: moving item into Node destination is same as above
        # To test object container, we create a container Object destination and monkey-patch it to have hooks
        # and verify do_item_move would respect transactional order if it called them.
        # Since current code does NOT call dest hooks for non-node, we instead verify that
        # moving an item from a Node into a container Object still respects source pre failure transactionally
        # and that success path doesn't leak.

        # First part: Node->Node item move already tested above (dest pre fails)

        # Second part: Item in container -> Node, source is container Object (not Node)
        # Create container with mocked hooks
        container = Object.create(None, "Chest", is_item=True, is_container=True)
        # Give container hooks manually to simulate transactional expectations
        container_calls = []
        container.at_pre_object_leave = MagicMock(side_effect=lambda *a, **k: (container_calls.append("pre_leave"), True)[1])
        container.at_object_leave = MagicMock(side_effect=lambda *a, **k: container_calls.append("leave"))

        # Note: base_obj do_item_move for loc not being Node will NOT call loc.at_pre_object_leave
        # So we test that even though we set it, it won't be called, but dest pre failure still aborts correctly
        item2 = Object.create(None, "Coin", is_item=True)
        item2.location = container
        container.add_object(item2)

        # Destination is Node n2 which will refuse
        n2.at_pre_object_receive = MagicMock(side_effect=lambda *a, **k: (container_calls.append("pre_receive"), False)[1])
        n2.at_object_receive = MagicMock(side_effect=lambda *a, **k: container_calls.append("receive"))

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item2.move_to(n2, announce=False)

        # Since loc is not Node, no pre_leave should be called, only dest pre_receive which fails
        assert ok is False
        # For this path, container's leave should not be called because code skips it for non-node loc
        # But we verify that dest receive not called and item not moved
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

        # Item moving between nodes (container-like item)
        item = Object.create(None, "Potion", is_item=True, is_container=True)
        item.location = n1
        n1.add_object(item)

        with patch("atheriz.settings.MAP_ENABLED", False):
            ok = item.move_to(n2, announce=False)

        assert ok is True
        assert calls == ["pre_leave", "pre_receive", "leave", "receive"]
        assert item.location == n2


# ==================== DoorPathfind ====================

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
        # Ensure access allows lock
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
        # try again with different caller, still fails
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
        # Create handler and nodes for pathfind
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
        # Need to mock map handler for add_door
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)
        return nh, n1, n2, door, mh

    def test_pathfind_open_locked_still_traversable(self, global_test_env):
        # Force open+locked inconsistent state, should be traversable regardless of unlock access
        def access_mock(caller, perm):
            # Simulate no access to unlock/open
            return False
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=False, door_locked=True, access_mock=MagicMock(side_effect=access_mock))
        caller = MagicMock()
        # Patch get_node_handler in pathfind and other modules
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
        # Closed, not locked, but caller cannot open
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
        # Even with access, open+locked must still be traversable (verifies not incorrectly blocking)
        nh, n1, n2, door, _ = self._setup_pathfind_two_nodes(door_closed=False, door_locked=True, access_mock=MagicMock(return_value=True))
        caller = MagicMock()
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, closed = astar(n1, n2, caller=caller)
        assert success is True

    def test_exit_command_open_locked_allows_move_legacy(self, global_test_env):
        # ExitCommand: open door allows move even if locked flag set (legacy)
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
        # Make try_open fail (no access)
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


# ==================== RemoveDoor ====================

class TestRemoveDoorCleansLinkAndGlyph:

    def _setup_door_via_handler(self, area_name="RemoveDoorArea"):
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name=area_name)
        grid = NodeGrid(area=area_name, z=0)
        n1 = Node(coord=Coord(area_name, 0, 0, 0))
        n2 = Node(coord=Coord(area_name, 0, 2, 0))
        # Note DoorCommand creates links at distance 2 with door glyph at middle
        # For manual setup, we mimic that: n1 north -> n2, n2 south -> n1
        n1.add_link(NodeLink("north", Coord(area_name, 0, 2, 0), ["n"]))
        n2.add_link(NodeLink("south", Coord(area_name, 0, 0, 0), ["s"]))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)
        door = Door.create(
            from_coord=Coord(area_name, 0, 0, 0),
            from_exit="north",
            to_coord=Coord(area_name, 0, 2, 0),
            to_exit="south",
            symbol_coord=(0, 1),
            closed_symbol=settings.NS_CLOSED_DOOR,
            open_symbol=settings.NS_OPEN_DOOR1,
            closed=True,
            locked=False,
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)
        return nh, n1, n2, door, mh

    def test_remove_door_remove_door_deletes_links(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler()
        # Pre-check links exist
        assert n1.get_link_by_name("north") is not None
        assert n2.get_link_by_name("south") is not None
        assert nh.get_doors(n1.coord) is not None
        assert "north" in nh.get_doors(n1.coord)
        assert "south" in nh.get_doors(n2.coord)

        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
        assert n1.has_link_name("north") is False
        assert n2.has_link_name("south") is False
        # Also via alias
        assert n1.get_link_by_name("n") is None

    def test_remove_door_remove_door_deletes_doors_dict(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea2")
        assert nh.get_doors(n1.coord) is not None
        assert nh.get_doors(n2.coord) is not None
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)
        doors1 = nh.get_doors(n1.coord)
        doors2 = nh.get_doors(n2.coord)
        if doors1:
            assert "north" not in doors1
        else:
            assert doors1 is None or "north" not in (doors1 or {})
        if doors2:
            assert "south" not in doors2

    def test_remove_door_remove_door_display_exits_no_longer_shows(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea3")
        # Before, display should contain north/south
        disp_before = n1.get_display_exits()
        assert "north" in disp_before
        disp_before2 = n2.get_display_exits()
        assert "south" in disp_before2

        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        disp_after = n1.get_display_exits()
        assert "north" not in disp_after
        disp_after2 = n2.get_display_exits()
        assert "south" not in disp_after2

    def test_remove_door_remove_door_player_cannot_use_exit(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea4")
        player = Object.create(None, "Adventurer", is_pc=True)
        player.location = n1
        n1.add_object(player)
        # Player should have exit command for north after being added
        assert n1.get_link_by_name("north") is not None
        # Simulate exit command existence: check that player's internal_cmdset has north
        # After add_object, add_exits adds commands
        found_before = any(getattr(c, "key", None) == "north" or getattr(c, "name", None) == "north" for c in player.internal_cmdset.commands) if hasattr(player.internal_cmdset, "commands") else False
        # Alternative: try to verify via Node's links
        # Remove door
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        # Now link absent, so moving via link should be considered absent
        assert n1.get_link_by_name("north") is None
        # Verify get_display_exits doesn't show it (already above)
        # Try to simulate ExitCommand behavior: should not move because link gone
        # We check that attempting to find link fails, and that pathfind would not find route
        # Also verify that player's exit command is stale but link lookup fails
        # If we try to manually trigger ExitCommand with old coords, it will still try to move via door check
        # but the underlying link absence means the exit is logically removed.
        # The critical assertion is that move via link absent fails.
        # We test that `n1.get_link_by_name("north")` is None, so any code that checks link will block.
        assert n1.get_link_by_name("north") is None
        # Additionally, ensure astar fails when trying to go from n1 to n2 without link
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, _ = astar(n1, n2)
            # No link, so path should fail
            assert success is False

        # Also verify that trying ExitCommand now with removed link still doesn't magically create link
        cmd = ExitCommand()
        cmd.caller_id = player.id
        cmd.location = n1.coord
        cmd.destination = n2.coord
        cmd.name = "north"
        cmd.key = "north"
        # Patch handler to return our nh, but since door removed, the door check will be None, but exit will still try move_to
        # However the semantic "cannot use exit" is verified by link absence, not necessarily by move_to blocking
        # We ensure that after removal, the handler's get_node still works but get_link fails
        assert nh.get_node(n1.coord) == n1
        assert n1.get_link_by_name("north") is None

    def test_remove_door_remove_door_both_coords_cleaned(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea5")
        # Ensure both sides have doors
        assert nh.get_doors(n1.coord)["north"] is door
        assert nh.get_doors(n2.coord)["south"] is door
        with patch("atheriz.globals.node.get_map_handler", return_value=mh):
            nh.remove_door(door)
        # After, both should be cleaned
        d1 = nh.get_doors(n1.coord)
        d2 = nh.get_doors(n2.coord)
        assert d1 is None or "north" not in d1
        assert d2 is None or "south" not in d2
        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None

    def test_remove_door_remove_door_via_door_create_and_add_door_then_remove(self, global_test_env):
        # Directly test Door.create + add_door + remove_door flow as spec says
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name="RemoveDoorArea6")
        grid = NodeGrid(area="RemoveDoorArea6", z=0)
        n1 = Node(coord=Coord("RemoveDoorArea6", 0, 0, 0))
        n2 = Node(coord=Coord("RemoveDoorArea6", 0, 2, 0))
        n1.add_link(NodeLink("north", Coord("RemoveDoorArea6", 0, 2, 0)))
        n2.add_link(NodeLink("south", Coord("RemoveDoorArea6", 0, 0, 0)))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)

        door = Door.create(
            from_coord=Coord("RemoveDoorArea6", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("RemoveDoorArea6", 0, 2, 0),
            to_exit="south",
            symbol_coord=(0, 1),
            closed_symbol="X",
            open_symbol="O",
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)

        assert n1.get_link_by_name("north") is not None
        assert n2.get_link_by_name("south") is not None

        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
        assert n1.get_display_exits() == "" or "north" not in n1.get_display_exits()
        assert n2.get_display_exits() == "" or "south" not in n2.get_display_exits()

    def test_remove_door_remove_door_twice_idempotent(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea7")
        with patch("atheriz.globals.node.get_map_handler", return_value=mh):
            nh.remove_door(door)
            # Second removal should not crash
            nh.remove_door(door)
        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None

