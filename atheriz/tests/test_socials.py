import pytest
from unittest.mock import MagicMock
from argparse import Namespace

from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_obj import Object
from atheriz.commands.loggedin.socials import CmdSocials

@pytest.fixture
def test_env():
    handler = NodeHandler()
    area = NodeArea(name="TestAreaSocials")
    grid = NodeGrid(z=0)
    
    room = Node(coord=("TestAreaSocials", 0, 0, 0))
    grid.add_node(room)
    area.add_grid(grid)
    handler.add_area(area)

    alice = Object.create(None, "Alice", is_pc=True)
    bob = Object.create(None, "Bob", is_pc=True)
    
    alice.location = room
    bob.location = room
    
    room.add_object(alice)
    room.add_object(bob)
    
    alice.msg = MagicMock()
    bob.msg = MagicMock()
    
    yield room, alice, bob
    
    # cleanup
    try:
        room.remove_object(alice)
        room.remove_object(bob)
    except:
        pass


def test_untargeted_social(test_env):
    room, alice, bob = test_env
    cmd = CmdSocials()
    
    args = Namespace(cmdstring="smile", target=[])
    cmd.run(alice, args)
    
    assert alice.msg.called
    alice_args, alice_kwargs = alice.msg.call_args
    alice_text = alice_args[0] if alice_args else alice_kwargs.get('text', '')
    if isinstance(alice_text, tuple): alice_text = alice_text[0]
    
    assert "You smile." in alice_text
    
    assert bob.msg.called
    bob_args, bob_kwargs = bob.msg.call_args
    bob_text = bob_args[0] if bob_args else bob_kwargs.get('text', '')
    if isinstance(bob_text, tuple): bob_text = bob_text[0]
    
    assert "Alice (offline) smiles." in bob_text


def test_targeted_social(test_env):
    room, alice, bob = test_env
    cmd = CmdSocials()
    
    alice.search = MagicMock(return_value=bob)
    
    args = Namespace(cmdstring="hug", target=["Bob"])
    cmd.run(alice, args)
    
    assert alice.msg.called
    alice_args, alice_kwargs = alice.msg.call_args
    alice_text = alice_args[0] if alice_args else alice_kwargs.get('text', '')
    if isinstance(alice_text, tuple): alice_text = alice_text[0]
    
    assert "You hug Bob (offline)." in alice_text
    
    assert bob.msg.called
    bob_args, bob_kwargs = bob.msg.call_args
    bob_text = bob_args[0] if bob_args else bob_kwargs.get('text', '')
    if isinstance(bob_text, tuple): bob_text = bob_text[0]
    
    assert "Alice (offline) hugs you." in bob_text

def test_missing_target_social(test_env):
    room, alice, bob = test_env
    cmd = CmdSocials()
    
    alice.search = MagicMock(return_value=None)
    
    args = Namespace(cmdstring="hug", target=["Charlie"])
    cmd.run(alice, args)
    
    assert not alice.msg.called
    assert not bob.msg.called
