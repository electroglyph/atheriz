import pytest
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel
from atheriz.objects.nodes import Node
from atheriz.singletons import objects
from atheriz.singletons.get import get_node_handler

@pytest.fixture(autouse=True)
def clear_registry():
    objects._ALL_OBJECTS.clear()
    objects._OBJECT_MAP.clear()
    objects.set_id(0)
    get_node_handler().clear()

class DeletionTestBase:
    def setup_method(self):
        # We need a caller for delete(caller, ...)
        self.caller = Object.create(None, "Caller")
        self.caller.privilege_level = 5 # superuser

def test_object_delete_basic():
    obj = Object.create(None, "Item")
    obj_id = obj.id
    assert objects.get(obj_id) == [obj]
    
    # Object.delete returns number of objects deleted
    caller = Object.create(None, "Caller")
    count = obj.delete(caller)
    assert count == 1
    assert objects.get(obj_id) == []
    assert obj.is_deleted is True

def test_object_delete_location_cleanup():
    container = Object.create(None, "Container", is_container=True)
    item = Object.create(None, "Item")
    item.move_to(container)
    assert item in container.contents
    
    caller = Object.create(None, "Caller")
    item.delete(caller)
    assert item not in container.contents
    assert item.location is None

def test_object_delete_recursive():
    container = Object.create(None, "Container", is_container=True)
    item1 = Object.create(None, "Item1")
    item2 = Object.create(None, "Item2")
    item1.move_to(container)
    item2.move_to(container)
    
    caller = Object.create(None, "Caller")
    count = container.delete(caller, recursive=True)
    assert count == 3 # container + 2 items
    assert objects.get(container.id) == []
    assert objects.get(item1.id) == []
    assert objects.get(item2.id) == []

def test_object_delete_non_recursive():
    room = Object.create(None, "Room", is_container=True)
    container = Object.create(None, "Container", is_container=True)
    item = Object.create(None, "Item")
    
    container.move_to(room)
    item.move_to(container)
    
    assert item in container.contents
    
    caller = Object.create(None, "Caller")
    # Non-recursive delete moves contents to container's location
    count = container.delete(caller, recursive=False)
    assert count == 2 # Moved item + deleted container
    assert objects.get(container.id) == []
    assert item.location == room
    assert item in room.contents

def test_object_delete_at_delete_block():
    class BlockedObject(Object):
        def at_delete(self, caller):
            return False
            
    obj = BlockedObject.create(None, "Blocked")
    caller = Object.create(None, "Caller")
    count = obj.delete(caller)
    assert count == 0
    assert objects.get(obj.id) == [obj]

def test_account_delete():
    acc = Account.create("TestAcc", "password")
    assert objects.get(acc.id) == [acc]
    
    caller = Object.create(None, "Caller")
    count = acc.delete(caller, False)
    assert count == 1
    assert objects.get(acc.id) == []
    assert acc.is_deleted is True

def test_channel_delete():
    chan = Channel.create("TestChan")
    assert objects.get(chan.id) == [chan]
    
    caller = Object.create(None, "Caller")
    count = chan.delete(caller, False)
    assert count == 1
    assert objects.get(chan.id) == []
    assert chan.is_deleted is True

def test_node_delete_basic():
    nh = get_node_handler()
    coord = ("test", 0, 0, 0)
    node = Node(coord=coord, desc="Test Node")
    nh.add_node(node)
    assert nh.get_node(coord) == node
    
    caller = Object.create(None, "Caller")
    node.delete(caller)
    assert nh.get_node(coord) is None
    assert node.is_deleted is True

def test_node_delete_recursive():
    nh = get_node_handler()
    coord = ("test", 1, 1, 1)
    node = Node(coord=coord)
    nh.add_node(node)
    
    item = Object.create(None, "Item")
    item.move_to(node)
    assert item in node.contents
    
    caller = Object.create(None, "Caller")
    # Node.delete(recursive=True) deletes all objects in the node
    # Note: Node.delete(recursive=True) calls item.delete(True)
    count = node.delete(caller, recursive=True)
    assert count == 1 # number of objects deleted (the item)
    assert nh.get_node(coord) is None
    assert objects.get(item.id) == []

def test_node_delete_non_recursive():
    nh = get_node_handler()
    coord = ("test", 2, 2, 2)
    node = Node(coord=coord)
    nh.add_node(node)
    
    home_node = Node(coord=("test", 0, 0, 0))
    nh.add_node(home_node)
    
    item = Object.create(None, "Item")
    item.home = home_node
    item.move_to(node)
    
    caller = Object.create(None, "Caller")
    # Node.delete(recursive=False) moves objects back home
    count = node.delete(caller, recursive=False)
    assert count == 1 # object moved home
    assert nh.get_node(coord) is None
    assert item.location == home_node
    assert objects.get(item.id) == [item]
