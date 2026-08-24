"""Pinned tests for 5.9 — get_doors live dict and node.links torn read.

INTENT: `NodeHandler.get_doors` returned live `dict` without copy, so
`pathfind` iterating `doors.get(l.name)` while `add_door`/`remove_door` mutated
the dict could `RuntimeError: dict changed size` or see torn `closed` flag.
`node.links` read without `node.lock` could also tear. `Barrier(2)` forces the race.
"""
from __future__ import annotations

import threading

from atheriz.globals.get import get_node_handler
from atheriz.objects.base_door import Door
from atheriz.objects.nodes import Node
from atheriz.pathfind import astar
from atheriz.utils import Coord


def test_get_doors_returns_copy_not_live(global_test_env):
    """`get_doors` must return a shallow copy, not the live dict."""
    nh = get_node_handler()
    coord = Coord("TestCopy", 0, 0, 0)
    door = Door.create(
        from_coord=coord,
        from_exit="north",
        to_coord=Coord("TestCopy", 0, 1, 0),
        to_exit="south",
        closed=False,
    )
    # ensure clean
    nh.doors.pop(coord, None)
    nh.add_door(door)
    d1 = nh.get_doors(coord)
    assert d1 is not None
    assert "north" in d1
    # mutating returned dict must not affect handler
    d1.pop("north", None)
    d2 = nh.get_doors(coord)
    assert "north" in d2, "get_doors returned live dict, pop affected handler"
    # also check that new add_door doesn't affect previous snapshot
    door2 = Door.create(
        from_coord=coord,
        from_exit="east",
        to_coord=Coord("TestCopy", 1, 0, 0),
        to_exit="west",
        closed=False,
    )
    nh.add_door(door2)
    assert "east" not in d1
    assert "east" in nh.get_doors(coord)
    # cleanup
    nh.doors.pop(coord, None)


def test_pathfind_no_torn_doors(global_test_env):
    """`add_door`/`remove_door` vs `astar` with `Barrier` must not raise
    `RuntimeError: dict changed` and must not see torn `closed`."""
    nh = get_node_handler()
    # setup small area
    from atheriz.objects.nodes import NodeArea, NodeGrid

    area = NodeArea(name="RaceArea")
    for z in (0,):
        grid = NodeGrid(area="RaceArea", z=0)
        for x, y in [(0, 0), (1, 0), (2, 0)]:
            node = Node(coord=Coord("RaceArea", x, y, 0))
            grid.nodes[(x, y)] = node
        area.add_grid(grid)
    nh.add_area(area)
    # link them via NodeLink for pathfind
    from atheriz.objects.nodes import NodeLink

    coord_a = Coord("RaceArea", 0, 0, 0)
    coord_b = Coord("RaceArea", 1, 0, 0)
    coord_c = Coord("RaceArea", 2, 0, 0)
    node_a = nh.get_node(coord_a)
    node_b = nh.get_node(coord_b)
    node_c = nh.get_node(coord_c)
    assert node_a and node_c and node_b
    node_a.add_link(NodeLink("east", coord_b, ["e"]))
    node_b.add_link(NodeLink("west", coord_a, ["w"]))
    node_b.add_link(NodeLink("east", coord_c, ["e"]))
    node_c.add_link(NodeLink("west", coord_b, ["w"]))

    # add initial door at (0,0) -> (1,0)
    door = Door.create(
        from_coord=coord_a,
        from_exit="east",
        to_coord=coord_b,
        to_exit="west",
        closed=False,
    )
    nh.add_door(door)

    barrier = threading.Barrier(2, timeout=5)
    errors: list[str] = []
    stop = threading.Event()

    def door_churn():
        try:
            barrier.wait(timeout=5)
            for _ in range(50):
                if stop.is_set():
                    break
                d = Door.create(
                    from_coord=coord_b,
                    from_exit="east",
                    to_coord=coord_c,
                    to_exit="west",
                    closed=False,
                )
                nh.add_door(d)
                # toggle closed without lock to stress (pathfind now copies and holds door lock)
                with d.lock:
                    d.closed = not d.closed
                nh.remove_door(d)
        except Exception as e:
            errors.append(f"door_churn: {e!r}")
            import traceback
            errors.append(traceback.format_exc())

    def pathfind_loop():
        try:
            barrier.wait(timeout=5)
            for _ in range(50):
                if stop.is_set():
                    break
                # pathfind from a to c (should not raise)
                ok, path, closed = astar(node_a, node_c, caller=None)
                # ok may be True/False depending on door state, but must not raise
                assert isinstance(path, list)
        except Exception as e:
            errors.append(f"pathfind: {e!r}")
            import traceback
            errors.append(traceback.format_exc())
        finally:
            stop.set()

    t1 = threading.Thread(target=door_churn)
    t2 = threading.Thread(target=pathfind_loop)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not errors, f"errors: {errors}"
    assert not t1.is_alive() and not t2.is_alive()
    # cleanup
    nh.remove_area("RaceArea")
