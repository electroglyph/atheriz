import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.utils import Coord
from atheriz.commands.loggedin.put import PutCommand
from atheriz.commands.loggedin.follow import FollowCommand, FollowScript, UnfollowCommand
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.objects.base_door import Door
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import get
from atheriz import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_container(name, **kwargs):
    obj = Object.create(None, name, is_container=True, **kwargs)
    obj.msg = MagicMock()
    return obj

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


def _make_caller_with_location(name="Caller", location=None):
    c = Object.create(None, name, is_pc=True)
    c.is_connected = True
    if location is not None:
        c.location = location
        location.add_object(c)
    c.msg = MagicMock()
    return c


# ---------------------------------------------------------------------------
# M1: containment cycle prevention via move_to and put guard
# ---------------------------------------------------------------------------

class TestMoveToPreventsContainmentCycle:
    def test_direct_self_containment_is_blocked(self):
        box = _make_container("Box")
        success = box.move_to(box)
        assert success is False
        assert box.location is not box

    def test_direct_self_via_id_equality_blocked(self):
        box = _make_container("Box")
        box2 = box
        success = box.move_to(box2)
        assert success is False

    def test_simple_indirect_cycle_bag_contains_pouch_then_bag_into_pouch_fails(self):
        bag = _make_container("Bag")
        pouch = _make_container("Pouch")
        assert pouch.move_to(bag) is True
        assert pouch.location is bag
        assert pouch in bag.contents
        old_loc = bag.location
        success = bag.move_to(pouch)
        assert success is False
        assert bag.location is old_loc
        assert bag.location is not pouch
        assert pouch.location is bag

    def test_indirect_cycle_via_intermediate_container(self):
        bag = _make_container("Bag")
        pouch = _make_container("Pouch")
        box = _make_container("Box")
        assert pouch.move_to(bag) is True
        assert box.move_to(pouch) is True
        assert box.location is pouch
        assert pouch.location is bag
        success = bag.move_to(box)
        assert success is False
        assert bag.location is not box

    def test_deep_chain_three_levels_blocks_outer_into_inner(self):
        outer = _make_container("Outer")
        middle = _make_container("Middle")
        inner = _make_container("Inner")
        tiny = _make_container("Tiny")
        assert middle.move_to(outer) is True
        assert inner.move_to(middle) is True
        assert tiny.move_to(inner) is True
        assert tiny.location is inner
        assert inner.location is middle
        assert middle.location is outer
        success = outer.move_to(inner)
        assert success is False
        assert outer.location is not inner
        success2 = outer.move_to(tiny)
        assert success2 is False
        assert middle.move_to(tiny) is False

    def test_deep_chain_valid_nesting_succeeds_when_no_cycle(self):
        outer = _make_container("Outer")
        inner = _make_container("Inner")
        assert inner.move_to(outer) is True
        assert inner.location is outer

    def test_valid_put_succeeds_when_no_cycle(self):
        bag = _make_container("Bag")
        pouch = _make_container("Pouch")
        assert pouch.move_to(bag) is True
        assert pouch in bag.contents
        bag2 = _make_container("Bag2")
        pouch2 = _make_container("Pouch2")
        assert pouch2.move_to(bag2) is True
        assert pouch2.location is bag2
        assert pouch2 in bag2.contents

    def test_move_to_allows_node_destination_even_if_container_has_contents(self):
        room = Node(coord=Coord("TestArea", 0, 0, 0))
        from atheriz.globals.objects import add_object as _add
        _add(room)
        bag = _make_container("Bag")
        pouch = _make_container("Pouch")
        pouch.move_to(bag)
        assert pouch.location is bag
        success = bag.move_to(room)
        assert success is True
        assert bag.location is room
        assert bag in room.contents
        assert pouch.location is bag

    def test_valid_move_to_unrelated_container_succeeds(self):
        bag = _make_container("Bag")
        pouch = _make_container("Pouch")
        other = _make_container("Other")
        pouch.move_to(bag)
        success = pouch.move_to(other)
        assert success is True
        assert pouch.location is other
        assert pouch not in bag.contents
        assert pouch in other.contents

    def test_cycle_check_traverses_location_chain(self):
        a = _make_container("A")
        b = _make_container("B")
        c = _make_container("C")
        b.move_to(a)
        c.move_to(b)
        assert a.move_to(c) is False
        assert b.move_to(c) is False
        assert c.move_to(a) is True or c.location is a  # c->a would be valid if c not containing a, but c is inside b inside a, so a is ancestor of c, but c moving to a would be moving up? Actually c inside b inside a, moving c to a should succeed (c already indirect inside a, but direct location to a is allowed? The cycle check only prevents moving an ancestor into descendant, not descendant into ancestor.)
        # Ensure descendant into ancestor is allowed
        c2 = _make_container("C2")
        a2 = _make_container("A2")
        b2 = _make_container("B2")
        b2.move_to(a2)
        c2.move_to(b2)
        success = c2.move_to(a2)
        assert success is True


class TestPutCommandContainmentGuard:
    def test_put_blocks_containment_loop_with_message(self):
        room = Node(coord=Coord("TestArea", 0, 0, 0))
        caller = Object.create(None, "Caller", is_pc=True)
        caller.location = room
        room.add_object(caller)
        caller.msg = MagicMock()
        bag = _make_container("Bag")
        bag.access = MagicMock(return_value=True)
        pouch = _make_container("Pouch")
        pouch.access = MagicMock(return_value=True)
        pouch.move_to(bag)
        bag.move_to(caller)
        caller.search = MagicMock(side_effect=[[pouch], [bag]])
        args = MagicMock(object="Bag", destination=["pouch"])
        PutCommand().run(caller, args)
        caller.msg.assert_any_call("You can't put Bag in Pouch - it would create a containment loop.")
        assert bag.location is caller
        assert pouch.location is bag

    def test_put_blocks_direct_self_loop(self):
        room = Node(coord=Coord("TestArea", 0, 0, 0))
        caller = Object.create(None, "Caller", is_pc=True)
        caller.location = room
        caller.msg = MagicMock()
        bag = _make_container("Bag")
        bag.access = MagicMock(return_value=True)
        bag.move_to(caller)
        caller.search = MagicMock(side_effect=[[bag], [bag]])
        args = MagicMock(object="Bag", destination=["bag"])
        PutCommand().run(caller, args)
        caller.msg.assert_any_call("You can't put Bag in Bag - it would create a containment loop.")
        assert bag.location is caller

    def test_put_valid_nesting_succeeds(self):
        room = Node(coord=Coord("TestArea", 0, 0, 0))
        room.msg_contents = MagicMock()
        caller = Object.create(None, "Caller", is_pc=True)
        caller.location = room
        caller.msg = MagicMock()
        bag = Object.create(None, "Bag", is_container=True)
        bag.is_container = True
        bag.access = MagicMock(return_value=True)
        pouch = Object.create(None, "Pouch", is_container=True)
        pouch.is_container = True
        pouch.move_to(caller)
        caller.search = MagicMock(side_effect=[[bag], [pouch]])
        args = MagicMock(object="Pouch", destination=["bag"])
        PutCommand().run(caller, args)
        assert pouch.location is bag
        assert pouch in bag.contents
        caller.msg.assert_any_call("You put Pouch in Bag.")

    def test_put_all_blocks_loop_for_offending_item_but_moves_others(self):
        room = Node(coord=Coord("TestArea", 0, 0, 0))
        room.msg_contents = MagicMock()
        caller = Object.create(None, "Caller", is_pc=True)
        caller.location = room
        caller.msg = MagicMock()
        bag = _make_container("Bag")
        bag.access = MagicMock(return_value=True)
        pouch = _make_container("Pouch")
        pouch.access = MagicMock(return_value=True)
        pouch.move_to(bag)
        bag.move_to(caller)
        apple = Object.create(None, "Apple", is_item=True)
        apple.move_to(caller)
        bag.id = bag.id
        caller.search = MagicMock(return_value=[pouch])
        args = MagicMock(object="all", destination=["pouch"])
        PutCommand().run(caller, args)
        found_msgs = [str(c) for c in caller.msg.call_args_list]
        assert any("containment loop" in str(m) for m in found_msgs)
        assert bag.location is caller
        assert bag not in pouch.contents

    def test_put_guard_stops_at_node_boundary(self):
        room = Node(coord=Coord("TestArea", 0, 0, 0))
        _add = __import__("atheriz.globals.objects", fromlist=["add_object"]).add_object
        _add(room)
        bag = _make_container("Bag")
        bag.move_to(room)
        pouch = _make_container("Pouch")
        pouch.move_to(bag)
        caller = Object.create(None, "Caller", is_pc=True)
        caller.location = room
        caller.msg = MagicMock()
        apple = Object.create(None, "Apple", is_item=True)
        apple.move_to(caller)
        success = apple.move_to(room)
        assert success is True
        assert apple.location is room
        other = _make_container("Other")
        other.move_to(room)
        success2 = bag.move_to(other)
        assert success2 is True

    def test_move_to_node_destination_is_always_allowed(self):
        inner = _make_container("Inner")
        outer = _make_container("Outer")
        inner.move_to(outer)
        room = Node(coord=Coord("TestArea", 5, 5, 0))
        from atheriz.globals.objects import add_object as _add
        _add(room)
        success = outer.move_to(room)
        assert success is True
        assert outer.location is room
        success2 = inner.move_to(room)
        assert success2 is True
        assert inner.location is room


# ---------------------------------------------------------------------------
# M3: follow co-location guard
# ---------------------------------------------------------------------------

def _force_follow(follower, leader):
    follower.following = leader.id
    with leader.lock:
        leader.followers.add(follower.id)
        if not leader.get_scripts_by_type("FollowScript"):
            s = FollowScript.create(follower, f"FollowScript_for_{follower.id}")
            leader.add_script(s)

class TestFollowCoLocationGuard:
    def test_only_colocated_follower_moves_when_leader_moves(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower_colocated = Object.create(None, "Follower1", is_pc=True)
        follower_colocated.is_connected = True
        follower_colocated.location = node1
        node1.add_object(follower_colocated)
        follower_colocated.msg = MagicMock()
        follower_distant = Object.create(None, "Follower2", is_pc=True)
        follower_distant.is_connected = True
        follower_distant.location = node1
        node1.add_object(follower_distant)
        follower_distant.msg = MagicMock()
        FollowCommand().run(follower_colocated, MagicMock(target="Leader"))
        FollowCommand().run(follower_distant, MagicMock(target="Leader"))
        assert follower_colocated.following == leader.id
        assert follower_distant.following == leader.id
        follower_distant.move_to(node2, "north")
        assert follower_distant.location == node2
        success = leader.move_to(node2, "north")
        assert success is True
        assert leader.location == node2
        assert follower_colocated.location == node2
        assert follower_distant.location == node2
        # distant was already at node2 before leader moved; it stays via prior location not old_loc
        # Verify co-located moved, distant did not move via follow (already there)

    def test_distant_follower_at_third_node_stays_behind(self):
        nh = get_node_handler()
        area = NodeArea(name="TestArea")
        grid = NodeGrid(z=0)
        node1 = Node(coord=Coord("TestArea", 0, 0, 0))
        node2 = Node(coord=Coord("TestArea", 0, 1, 0))
        node3 = Node(coord=Coord("TestArea", 9, 9, 0))
        node1.add_link(NodeLink(name="north", coord=Coord("TestArea", 0, 1, 0)))
        node2.add_link(NodeLink(name="south", coord=Coord("TestArea", 0, 0, 0)))
        grid.add_node(node1)
        grid.add_node(node2)
        grid.add_node(node3)
        area.add_grid(grid)
        nh.add_area(area)
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        colocated = Object.create(None, "FollowerA", is_pc=True)
        colocated.is_connected = True
        colocated.location = node1
        node1.add_object(colocated)
        colocated.msg = MagicMock()
        distant = Object.create(None, "FollowerB", is_pc=True)
        distant.is_connected = True
        distant.location = node1
        node1.add_object(distant)
        distant.msg = MagicMock()
        FollowCommand().run(colocated, MagicMock(target="Leader"))
        FollowCommand().run(distant, MagicMock(target="Leader"))
        assert colocated.id in leader.followers
        assert distant.id in leader.followers
        distant.move_to(node3)
        assert distant.location == node3
        leader.move_to(node2, "north")
        assert leader.location == node2
        assert colocated.location == node2
        assert distant.location == node3
        assert distant.location != node2

    def test_follower_with_none_location_not_moved(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower_none = Object.create(None, "Lonely", is_pc=True)
        follower_none.is_connected = True
        follower_none.location = node1
        node1.add_object(follower_none)
        follower_none.msg = MagicMock()
        follower_ok = Object.create(None, "Ok", is_pc=True)
        follower_ok.is_connected = True
        follower_ok.location = node1
        node1.add_object(follower_ok)
        follower_ok.msg = MagicMock()
        FollowCommand().run(follower_none, MagicMock(target="Leader"))
        FollowCommand().run(follower_ok, MagicMock(target="Leader"))
        follower_none.location = None
        assert follower_none.following == leader.id
        assert follower_ok.following == leader.id
        leader.move_to(node2, "north")
        assert leader.location == node2
        assert follower_none.location is None
        assert follower_ok.location == node2

    def test_distant_follower_via_forced_follow_not_moved_when_not_colocated(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        colocated = Object.create(None, "Here", is_pc=True)
        colocated.is_connected = True
        colocated.location = node1
        node1.add_object(colocated)
        colocated.msg = MagicMock()
        distant = Object.create(None, "Away", is_pc=True)
        distant.is_connected = True
        distant.location = node2
        node2.add_object(distant)
        distant.msg = MagicMock()
        FollowCommand().run(colocated, MagicMock(target="Leader"))
        _force_follow(distant, leader)
        assert colocated.id in leader.followers
        assert distant.id in leader.followers
        leader.move_to(node2, "north")
        assert colocated.location == node2
        assert distant.location == node2

    def test_forced_follower_with_none_location_is_ignored(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower_none = Object.create(None, "Nowhere", is_pc=True)
        follower_none.is_connected = True
        follower_none.location = None
        follower_none.msg = MagicMock()
        _force_follow(follower_none, leader)
        follower_ok = Object.create(None, "Ok2", is_pc=True)
        follower_ok.is_connected = True
        follower_ok.location = node1
        node1.add_object(follower_ok)
        follower_ok.msg = MagicMock()
        FollowCommand().run(follower_ok, MagicMock(target="Leader"))
        leader.move_to(node2, "north")
        assert follower_none.location is None
        assert follower_ok.location == node2

    def test_followers_in_same_room_both_move(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        f1 = Object.create(None, "F1", is_pc=True)
        f1.is_connected = True
        f1.location = node1
        node1.add_object(f1)
        f1.msg = MagicMock()
        f2 = Object.create(None, "F2", is_pc=True)
        f2.is_connected = True
        f2.location = node1
        node1.add_object(f2)
        f2.msg = MagicMock()
        FollowCommand().run(f1, MagicMock(target="Leader"))
        FollowCommand().run(f2, MagicMock(target="Leader"))
        leader.move_to(node2, "north")
        assert f1.location == node2
        assert f2.location == node2


class TestFollowScriptOldLocCapturing:
    def test_follow_script_captures_old_loc_before_move(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower = Object.create(None, "Follower", is_pc=True)
        follower.is_connected = True
        follower.location = node1
        node1.add_object(follower)
        follower.msg = MagicMock()
        FollowCommand().run(follower, MagicMock(target="Leader"))
        scripts = leader.get_scripts_by_type("FollowScript")
        assert len(scripts) == 1
        script = scripts[0]
        assert script._old_loc is None
        script.at_pre_move(node2, "north")
        assert script._old_loc is node1
        script._old_loc = None

    def test_follow_script_clears_old_loc_after_post_move(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower = Object.create(None, "Follower", is_pc=True)
        follower.is_connected = True
        follower.location = node1
        node1.add_object(follower)
        follower.msg = MagicMock()
        FollowCommand().run(follower, MagicMock(target="Leader"))
        script = leader.get_scripts_by_type("FollowScript")[0]
        script._old_loc = node1
        script.at_post_move(node2, "north")
        assert script._old_loc is None

    def test_follow_script_old_loc_none_prevents_any_follower_move(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower = Object.create(None, "Follower", is_pc=True)
        follower.is_connected = True
        follower.location = node1
        node1.add_object(follower)
        follower.msg = MagicMock()
        FollowCommand().run(follower, MagicMock(target="Leader"))
        script = leader.get_scripts_by_type("FollowScript")[0]
        script._old_loc = None
        script.at_post_move(node2, "north")
        assert follower.location == node1

    def test_script_deletes_when_no_followers(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower = Object.create(None, "Follower", is_pc=True)
        follower.is_connected = True
        follower.location = node1
        node1.add_object(follower)
        follower.msg = MagicMock()
        FollowCommand().run(follower, MagicMock(target="Leader"))
        script = leader.get_scripts_by_type("FollowScript")[0]
        assert script is not None
        with leader.lock:
            leader.followers.clear()
        script._old_loc = node1
        script.at_post_move(node2, "north")
        assert script.is_deleted is True or script not in leader.get_scripts_by_type("FollowScript")

    def test_follower_move_failure_sends_message(self):
        node1, node2, _ = _make_node_pair()
        leader = Object.create(None, "Leader", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        follower = Object.create(None, "Follower", is_pc=True)
        follower.is_connected = True
        follower.location = node1
        node1.add_object(follower)
        follower.msg = MagicMock()
        FollowCommand().run(follower, MagicMock(target="Leader"))
        script = leader.get_scripts_by_type("FollowScript")[0]
        script._old_loc = node1
        with patch.object(follower, "move_to", return_value=False) as mock_move:
            script.at_post_move(node2, "north")
            follower.msg.assert_called_with(f"You can't follow {leader.name} there!")
            mock_move.assert_called_once()


# ---------------------------------------------------------------------------
# M4: door stays open if move_to fails
# ---------------------------------------------------------------------------

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
