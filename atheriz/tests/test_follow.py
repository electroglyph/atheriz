import pytest
from unittest.mock import MagicMock
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.commands.loggedin.follow import FollowCommand, NoFollowCommand, FollowScript

def setup_test_nodes():
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    
    node1 = Node(coord=("TestArea", 0, 0, 0))
    link_n = NodeLink(name="north", coord=("TestArea", 0, 1, 0))
    node1.add_link(link_n)
    
    node2 = Node(coord=("TestArea", 0, 1, 0))
    link_s = NodeLink(name="south", coord=("TestArea", 0, 0, 0))
    node2.add_link(link_s)
    
    grid.add_node(node1)
    grid.add_node(node2)
    area.add_grid(grid)
    handler.add_area(area)
    return node1, node2

def test_follow_command():
    node1, _ = setup_test_nodes()
    
    leader = Object.create(None, "Leader", is_pc=True)
    leader.location = node1
    node1.add_object(leader)
    
    follower = Object.create(None, "Follower", is_pc=True)
    follower.location = node1
    node1.add_object(follower)
    
    follower.msg = MagicMock()
    
    cmd = FollowCommand()
    args = MagicMock(target="Leader")
    
    cmd.run(follower, args)
    
    assert follower.following == leader.id
    assert follower.id in leader.followers
    
    scripts = leader.get_scripts_by_type("FollowScript")
    assert len(scripts) == 1
    
def test_follow_multiple_followers():
    node1, node2 = setup_test_nodes()
    
    leader = Object.create(None, "Leader", is_pc=True)
    leader.location = node1
    node1.add_object(leader)
    
    f1 = Object.create(None, "F1", is_pc=True)
    f1.location = node1
    node1.add_object(f1)
    
    f2 = Object.create(None, "F2", is_pc=True)
    f2.location = node1
    node1.add_object(f2)
    
    # Use command to follow
    cmd = FollowCommand()
    
    cmd.run(f1, MagicMock(target="Leader"))
    cmd.run(f2, MagicMock(target="Leader"))
    
    assert len(leader.followers) == 2
    assert f1.id in leader.followers
    assert f2.id in leader.followers
    
    # Move the leader
    success = leader.move_to(node2, "north")
    assert success is True
    
    # Followers should have moved
    assert f1.location == node2
    assert f2.location == node2

def test_nofollow_command():
    node1, _ = setup_test_nodes()
    
    leader = Object.create(None, "Leader", is_pc=True)
    leader.location = node1
    node1.add_object(leader)
    
    f1 = Object.create(None, "F1", is_pc=True)
    f1.location = node1
    node1.add_object(f1)
    
    cmd = FollowCommand()
    cmd.run(f1, MagicMock(target="Leader"))
    
    assert len(leader.followers) == 1
    assert f1.following == leader.id
    assert len(leader.get_scripts_by_type("FollowScript")) == 1
    
    # Run nofollow
    nofollow_cmd = NoFollowCommand()
    nofollow_cmd.run(leader, None)
    
    assert leader.no_follow is True
    assert len(leader.followers) == 0
    assert f1.following is None
    assert len(leader.get_scripts_by_type("FollowScript")) == 0
    
    # Try following again when no_follow is True
    f1.msg = MagicMock()
    cmd.run(f1, MagicMock(target="Leader"))
    f1.msg.assert_called_with("Leader will not lead you.")
    
    # Toggle it off
    nofollow_cmd.run(leader, None)
    assert leader.no_follow is False

def test_cant_follow_self_or_nonexistent():
    node1, _ = setup_test_nodes()
    
    follower = Object.create(None, "Follower", is_pc=True)
    follower.location = node1
    node1.add_object(follower)
    
    cmd = FollowCommand()
    follower.msg = MagicMock()
    
    # Follow nonexistent
    cmd.run(follower, MagicMock(target="Nobody"))
    follower.msg.assert_called_with("Could not find 'Nobody'.")
    
    # Follow self
    cmd.run(follower, MagicMock(target="Follower"))
    follower.msg.assert_called_with("You can't follow yourself!")
    assert follower.following is None
    assert len(follower.followers) == 0
