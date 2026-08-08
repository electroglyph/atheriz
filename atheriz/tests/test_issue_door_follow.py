"""Issue tests: #34 — the follow-clearing that runs when moving through a plain
exit (exit.py:59-68) is skipped when moving through a *door*, because the door
branch (exit.py:49-58) `return`s before reaching it.

INTENT: following must be cleared on any occupants move, whether the exit
traversed is a plain link or a door, identically.
"""
from __future__ import annotations

from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeArea, NodeGrid
from atheriz.globals.node import NodeHandler
from atheriz.utils import Coord


class _Door:
    name = "iron_door"
    closed = True
    locked = False

    def try_open(self, caller):
        return True

    def try_close(self, caller):
        return None


def _make_area(nh: NodeHandler):
    src = Node(coord=Coord("a", 0, 0, 0))
    dest = Node(coord=Coord("a", 0, 1, 0))
    grid = NodeGrid(area="a", z=0)
    grid.add_node(src)
    grid.add_node(dest)
    area = NodeArea(name="a")
    area.add_grid(grid)
    nh.add_area(area)
    return src, dest


def test_door_passage_clears_following(global_test_env, monkeypatch):
    """INTENT: passing through an open door clears following, exactly like a
    plain exit does. Today the door branch drops the follower's following
    stays set -> the follower keeps tracking the leader through the wall."""
    nh = NodeHandler()
    src, dest = _make_area(nh)
    door = _Door()
    nh.doors[Coord("a", 0, 0, 0)] = {"iron_door": door}

    leader = Object.create(None, "Leader")
    follower = Object.create(None, "Follower")
    follower.move_to(src)

    monkeypatch.setattr("atheriz.commands.loggedin.exit.get_node_handler", lambda: nh)
    monkeypatch.setattr("atheriz.commands.loggedin.exit.get", lambda _id: [leader])

    follower.following = leader.id
    leader.followers = {follower.id}

    ex = ExitCommand()
    ex.caller_id = follower.id
    ex.location = Coord("a", 0, 0, 0)
    ex.destination = Coord("a", 0, 1, 0)
    ex.name = "iron_door"
    ex.do_move()

    assert follower.following is None, (
        "door passage must clear following the same way a plain exit does"
    )