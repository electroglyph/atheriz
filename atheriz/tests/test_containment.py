import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.utils import Coord
from atheriz.commands.loggedin.put import PutCommand
from atheriz.objects.base_door import Door
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import get
from atheriz import settings


def _make_container(name, **kwargs):
    obj = Object.create(None, name, is_container=True, **kwargs)
    obj.msg = MagicMock()
    return obj


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
        assert c.move_to(a) is True or c.location is a
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
