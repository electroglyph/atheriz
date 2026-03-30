import pytest
from unittest.mock import MagicMock
from atheriz.commands.loggedin.group import GroupCommand
from atheriz.objects.base_obj import Object
from atheriz.objects.base_channel import Channel
from atheriz.globals.objects import get

class MockArgs:
    def __init__(self, *args):
        self.args = list(args)

@pytest.fixture
def test_objects(db_setup):
    leader = Object.create(None, "Leader", is_npc=True)
    follower = Object.create(None, "Follower", is_npc=True)
    target = Object.create(None, "Target", is_npc=True)
    
    leader.msg = MagicMock()
    follower.msg = MagicMock()
    target.msg = MagicMock()
    
    # Leader needs to have followers to add them
    leader.followers = [follower.id, target.id]
    
    # Mock search so we don't need location logic
    def mock_search(term):
        if term == "Follower": return [follower]
        if term == "Target": return [target]
        if term == "Leader": return [leader]
        return []
        
    leader.search = MagicMock(side_effect=mock_search)
    follower.search = MagicMock(side_effect=mock_search)
    target.search = MagicMock(side_effect=mock_search)
    
    return leader, follower, target

def test_group_add(test_objects):
    leader, follower, _ = test_objects
    cmd = GroupCommand()
    
    cmd.run(leader, MockArgs("add", "Follower"))
    
    assert leader.group_channel is not None
    channel = get(leader.group_channel)[0]
    
    assert follower.id in channel.listeners
    assert leader.id in channel.listeners
    assert channel.created_by == leader.id
    assert follower.group_channel == channel.id

def test_group_add_not_following(test_objects):
    leader, follower, target = test_objects
    # followers doesn't include target
    leader.followers = [follower.id]
    
    cmd = GroupCommand()
    cmd.run(leader, MockArgs("add", "Target"))
    
    assert leader.group_channel is None
    assert "is not following you" in str(leader.msg.call_args)

def test_group_kick(test_objects):
    leader, follower, _ = test_objects
    cmd = GroupCommand()
    cmd.run(leader, MockArgs("add", "Follower"))
    
    channel = get(leader.group_channel)[0]
    assert follower.id in channel.listeners
    
    cmd.run(leader, MockArgs("kick", "Follower"))
    assert follower.id not in channel.listeners

def test_group_kick_not_leader(test_objects):
    leader, follower, _ = test_objects
    cmd = GroupCommand()
    cmd.run(leader, MockArgs("add", "Follower"))
    
    cmd.run(follower, MockArgs("kick", "Leader"))
    assert "You are not the leader" in str(follower.msg.call_args)

def test_group_leave(test_objects):
    leader, follower, _ = test_objects
    cmd = GroupCommand()
    cmd.run(leader, MockArgs("add", "Follower"))
    
    cmd.run(follower, MockArgs("leave"))
    
    channel = get(leader.group_channel)[0]
    assert follower.id not in channel.listeners
    assert follower.group_channel is None

def test_group_list(test_objects):
    leader, follower, target = test_objects
    cmd = GroupCommand()
    cmd.run(leader, MockArgs("add", "Follower"))
    cmd.run(leader, MockArgs("add", "Target"))
    
    cmd.run(leader, MockArgs("list"))
    
    call_args_str = str(leader.msg.call_args)
    assert "Leader" in call_args_str
    assert "Follower" in call_args_str
    assert "Target" in call_args_str

def test_group_message(test_objects):
    leader, follower, _ = test_objects
    cmd = GroupCommand()
    cmd.run(leader, MockArgs("add", "Follower"))
    
    leader.msg.reset_mock()
    follower.msg.reset_mock()
    
    cmd.run(leader, MockArgs("Hello", "team!"))
    
    leader_msg_call = str(leader.msg.call_args)
    follower_msg_call = str(follower.msg.call_args)
    
    assert "Hello team!" in leader_msg_call
    assert "Hello team!" in follower_msg_call
