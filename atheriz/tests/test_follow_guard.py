import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.utils import Coord
from atheriz.commands.loggedin.follow import FollowCommand, FollowScript, UnfollowCommand
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
