import pytest
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.singletons.node import NodeHandler
from atheriz.objects.base_obj import Object
from atheriz.singletons import objects as obj_singleton
from atheriz.database_setup import get_database
from atheriz import settings
from pathlib import Path
import shutil
from unittest.mock import MagicMock

TEST_SAVE_DIR = Path("test_move_data")

def test_npc_move_announcements():
    # 1. Setup Area, Grid, Nodes
    handler = NodeHandler()
    area = NodeArea(name="TestArea")
    grid = NodeGrid(z=0)
    
    # Node 1 (Source)
    node1 = Node(coord=("TestArea", 0, 0, 0))
    link_n = NodeLink(name="north", coord=("TestArea", 0, 1, 0))
    node1.add_link(link_n)
    
    # Node 2 (Destination)
    node2 = Node(coord=("TestArea", 0, 1, 0))
    link_s = NodeLink(name="south", coord=("TestArea", 0, 0, 0))
    node2.add_link(link_s)
    
    grid.add_node(node1)
    grid.add_node(node2)
    area.add_grid(grid)
    handler.add_area(area)

    # 2. Setup Objects
    # NPC moving
    mover = Object.create(None, "MoverNPC", is_npc=True)
    mover.location = node1
    node1.add_object(mover)

    # Observer in source (Node 1)
    observer1 = Object.create(None, "Observer1", is_pc=True)
    observer1.location = node1
    node1.add_object(observer1)
    
    # Observer in destination (Node 2)
    observer2 = Object.create(None, "Observer2", is_pc=True)
    observer2.location = node2
    node2.add_object(observer2)

    # Mock msg to capture output
    observer1.msg = MagicMock()
    observer2.msg = MagicMock()

    # 3. Execute Move
    # Move mover north to node2
    success = mover.move_to(node2, to_exit="north")
    
    assert success is True
    assert mover.location == node2
    
    # 4. Verify Messages
    
    # Observer 1 (at source) should see mover leaving north
    # "MoverNPC leaves to the north."
    # The actual message format from base_obj.py: "$You(mover) $conj({self.move_verb}) {to_str}."
    # to_str for "north" is "to the north"
    # default move_verb is "walk" -> "walks"
    # So: "MoverNPC walks to the north."
    
    # We check if msg was called. It's usually called with text=(message, kwargs) or just string.
    # The msg_contents parsing happens before .msg(), so .msg() receives the final string.
    
    # Let's inspect the call args for observer1
    assert observer1.msg.called
    args, call_kwargs = observer1.msg.call_args
    msg_text = args[0] if args else call_kwargs.get('text', '')
    if isinstance(msg_text, tuple): msg_text = msg_text[0]
    
    assert "MoverNPC" in msg_text
    assert "walks" in msg_text or "leaves" in msg_text # checking for likely verbs
    assert "north" in msg_text
    assert "away" not in msg_text # Ensure it's not the generic 'away' message

    # Observer 2 (at dest) should see mover arriving from south
    # "MoverNPC arrives from the south."
    # from_exit logic:
    # get_reverse_link(node1 (0,0,0), node2 (0,1,0)) -> should find link to (0,0,0) which is "south"
    # base_obj: "$You(mover) $conj({self.move_verb}) in {from_str}."
    # from_str for "south" is "from the south"
    # "MoverNPC walks in from the south."

    assert observer2.msg.called
    args2, call_kwargs2 = observer2.msg.call_args
    msg_text2 = args2[0] if args2 else call_kwargs2.get('text', '')
    if isinstance(msg_text2, tuple): msg_text2 = msg_text2[0]
    
    assert "MoverNPC" in msg_text2
    assert "walks" in msg_text2 or "arrives" in msg_text2
    assert "south" in msg_text2

def test_move_into_container():
    container = Object.create(None, "Backpack", is_item=True, is_container=True)
    item = Object.create(None, "Apple", is_item=True)
    
    success = item.move_to(container)
    
    assert success is True
    assert item.location == container
    assert item.id in container._contents
    assert item in container.contents

def test_move_between_containers():
    c1 = Object.create(None, "Backpack", is_item=True, is_container=True)
    c2 = Object.create(None, "Chest", is_item=True, is_container=True)
    item = Object.create(None, "Apple", is_item=True)
    
    item.move_to(c1)
    assert item.location == c1
    
    success = item.move_to(c2)
    assert success is True
    assert item.location == c2
    assert item.id not in c1._contents
    assert item.id in c2._contents

def test_move_into_object_with_lock():
    container = Object.create(None, "LockedBox", is_item=True, is_container=True)
    item = Object.create(None, "Gold", is_item=True)
    
    # Add a lock that always fails
    container.add_lock("put", lambda x: False)
    
    success = item.move_to(container)
    assert success is False
    assert item.location is None

def test_move_hooks():
    container = Object.create(None, "MagicBox", is_item=True, is_container=True)
    item = Object.create(None, "Wand", is_item=True)
    
    item.at_pre_move = MagicMock(return_value=True)
    item.at_post_move = MagicMock()
    
    success = item.move_to(container)
    
    assert success is True
    item.at_pre_move.assert_called_with(container, None)
    # Note: at_post_move is NOT called in non-node moves in base_obj.py
    # So we don't assert it here for container moves.
    
    # Test pre_move blocking
    item2 = Object.create(None, "CursedSword", is_item=True)
    item2.at_pre_move = MagicMock(return_value=False)
    
    success2 = item2.move_to(container)
    assert success2 is False
    assert item2.location is None

def test_nested_containers():
    outer = Object.create(None, "LargeChest", is_item=True, is_container=True)
    inner = Object.create(None, "SmallBox", is_item=True, is_container=True)
    item = Object.create(None, "Gem", is_item=True)
    
    # item -> inner
    item.move_to(inner)
    # inner -> outer
    success = inner.move_to(outer)
    
    assert success is True
    assert inner.location == outer
    assert item.location == inner
    assert inner.id in outer._contents
    assert item.id in inner._contents
