"""Issue tests: #17 — `move_to` writes `last_touched_by = destination.id`
(base_obj.py:961), but `Node.id` is hard-coded to `-1` (nodes.py:149), so every
move into a room sets `last_touched_by = -1` and the "last touched" field
(exam.py:105) is meaningless.

INTENT: nodes must carry real, unique ids so `last_touched_by` reflects the
room that was entered.
"""
from __future__ import annotations

from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


def test_node_ids_are_real(global_test_env):
    """INTENT: nodes are assigned unique ids (not the hard-coded -1)."""
    node = Node(coord=Coord("test", 1, 1, 0))
    assert node.id != -1, "node ids are hard-coded to -1 (nodes.py:149)"


def test_move_into_room_sets_meaningful_last_touched(global_test_env):
    """INTENT: moving into a room must record the room's real id in
    `last_touched_by`. Today the destination id is -1, so the field is
    meaningless -> FAIL."""
    node = Node(coord=Coord("test", 2, 2, 0))
    walker = Object.create(None, "walker")
    walker.move_to(node)
    assert walker.location is node
    assert walker.last_touched_by != -1, "last_touched_by stayed -1 after entering a room"
    assert walker.last_touched_by == node.id