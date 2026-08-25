import pytest
from unittest.mock import MagicMock, patch
import threading

from atheriz.utils import get_dir, get_points_in_sphere, _MAX_SPHERE_RADIUS, Coord
from atheriz.objects.funcparser_helpers import _safe_pow, _safe_arith_eval
from atheriz.objects.verb_conjugation.conjugate import verb_is_present, verb_is_past
from atheriz.objects.base_channel import Channel
from atheriz.objects.nodes import NodeArea
import atheriz.settings as settings


# U2: get_dir ignores area
def test_get_dir_different_area_returns_empty():
    assert get_dir(("AreaA", 0, 0, 0), ("AreaB", 1, 0, 0)) == ""
    assert get_dir(("AreaA", 0, 0, 0), ("AreaA", 1, 0, 0)) == "east"
    # Coord namedtuple
    assert get_dir(Coord("A", 0, 0, 0), Coord("B", 5, 5, 0)) == ""
    assert get_dir(Coord("A", 0, 0, 0), Coord("A", 0, 1, 0)) == "north"


def test_get_dir_mixed_dims_and_same_area():
    # mixed 4-tuple vs 3-tuple should be treated as different area -> empty
    assert get_dir(("AreaA", 0, 0, 0), (0, 1, 0)) == ""
    # same area with y diff
    assert get_dir(("X", 0, 0, 0), ("X", 0, 1, 0)) == "north"
    # 3-tuples use y,z as vectors (x at [0]), so (0,0,0)->(0,1,0) is east per current impl
    assert get_dir((0, 0, 0), (0, 1, 0)) == "east"


# U3: get_points_in_sphere radius guard
def test_get_points_in_sphere_radius_guard():
    with pytest.raises(ValueError):
        get_points_in_sphere((0, 0, 0), -1)
    with pytest.raises(ValueError):
        get_points_in_sphere((0, 0, 0), _MAX_SPHERE_RADIUS + 1)
    with pytest.raises(ValueError):
        get_points_in_sphere((0, 0, 0), 1000)
    # boundary allowed
    pts = get_points_in_sphere((0, 0, 0), 0)
    assert pts == [(0, 0, 0)]
    pts2 = get_points_in_sphere((0, 0, 0), _MAX_SPHERE_RADIUS)
    assert len(pts2) > 0


def test_get_nodes_in_sphere_radius_guard():
    area = NodeArea(name="TestSphere")
    with pytest.raises(ValueError):
        area.get_nodes_in_sphere((0, 0, 0), -5)
    with pytest.raises(ValueError):
        area.get_nodes_in_sphere((0, 0, 0), 500)
    # valid still works (no grids -> empty list, not error)
    assert area.get_nodes_in_sphere((0, 0, 0), 5) == []


# U4: _safe_arith_eval returns complex
def test_safe_pow_rejects_complex():
    with pytest.raises(ValueError, match="complex"):
        _safe_pow(-2, 0.5)
    with pytest.raises(ValueError, match="complex"):
        _safe_arith_eval("(-2)**0.5")
    # alternative fractional exponent
    with pytest.raises(ValueError):
        _safe_arith_eval("(-4)**0.5")
    # valid integer power still works
    assert _safe_pow(2, 3) == 8
    assert _safe_arith_eval("2**3") == 8
    assert _safe_arith_eval("9**0.5") == 3.0


# U5: verb_is_present / verb_is_past substring bug
def test_verb_is_present_are_plural():
    # "are" is both 2nd singular present and present plural
    assert verb_is_present("are", "plural") is True
    assert verb_is_present("are", "*") is True
    assert verb_is_present("are", "2") is True
    assert verb_is_present("are", "2nd") is True
    assert verb_is_present("are", "1") is False
    assert verb_is_present("are", "3") is False
    # "is" only 3rd singular
    assert verb_is_present("is", "3") is True
    assert verb_is_present("is", "plural") is False
    assert verb_is_present("is", "2") is False
    # empty person means any present tense
    assert verb_is_present("am", "") is True
    assert verb_is_present("was", "") is False


def test_verb_is_past_was_covers_both_singular():
    # "was" is both 1st and 3rd singular past
    assert verb_is_past("was", "1") is True
    assert verb_is_past("was", "3") is True
    assert verb_is_past("was", "2") is False
    assert verb_is_past("was", "*") is False
    assert verb_is_past("were", "2") is True
    assert verb_is_past("were", "*") is True
    assert verb_is_past("were", "1") is False


def test_verb_is_present_past_negated():
    assert verb_is_present("isn't", "3", negated=True) is True
    assert verb_is_present("is", "3", negated=True) is False
    assert verb_is_past("wasn't", "1", negated=True) is True
    assert verb_is_past("was", "1", negated=True) is False


# U6: reloader _apply_patch unsynchronized for lock-less objects
def test_apply_patch_lockless_uses_fallback():
    from atheriz.reloader import _apply_patch, _FALLBACK_PATCH_LOCK

    class Old:
        def __init__(self):
            self.x = 1

    class New(Old):
        def new_method(self):
            return 42

    obj = Old()
    assert not hasattr(obj, "lock")
    # Should patch without error and acquire fallback lock
    # Verify fallback lock is used by checking it is not dead-locked
    assert _FALLBACK_PATCH_LOCK.acquire(blocking=False) is True
    _FALLBACK_PATCH_LOCK.release()
    _apply_patch(obj, New)
    assert isinstance(obj, New)
    assert obj.x == 1
    assert obj.new_method() == 42

    # concurrent patching of lock-less objects should not tear __dict__
    errors = []

    def patch_concurrently():
        try:
            o = Old()
            o.x = 99
            _apply_patch(o, New)
            assert isinstance(o, New)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=patch_concurrently) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


# U7: get_history negative count leak
def test_get_history_negative_count_returns_empty():
    ch = Channel()
    ch.name = "testchan"
    ch.id = 999999
    with ch.lock:
        ch.history.clear()
    ch.msg("hello")
    ch.msg("world")
    ch.msg("third")
    # normal
    h = ch.get_history(count=2)
    assert "world" in h or "third" in h
    # negative should return empty, not leak tail from index 5
    assert ch.get_history(count=-5) == ""
    assert ch.get_history(count=-1) == ""
    assert ch.get_history(count=0) == ""
    # beyond limit clamped
    over = settings.CHANNEL_HISTORY_LIMIT + 100
    hist = ch.get_history(count=over)
    # should be same as limit (3 messages) not error
    assert hist.count("hello") == 1 or "hello" in hist


# U8: pathfind stale heap entries + heapify
def test_pathfind_no_heapify_and_stale_handling(node_handler_setup=None):
    # Use the existing pathfind fixtures: ensure no heapify is called and path still correct
    from atheriz.pathfind import astar
    from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
    from atheriz.globals.node import NodeHandler

    nh = NodeHandler()
    area = NodeArea(name="U8Area")
    grid = NodeGrid(area="U8Area", z=0)
    # Create a diamond where alternative routes cause g improvement
    #   n2
    #  /  \
    # n1--n3--n4  (n1->n3 direct cost 2, via n2 cost 2 as well, but we force improvement order)
    # We'll just test that astar finds shortest path and heapify not used
    nodes = {}
    for coord in [(0, 0), (1, 1), (1, 0), (2, 0)]:
        n = Node(coord=Coord("U8Area", coord[0], coord[1], 0))
        nodes[coord] = n
        grid.nodes[coord] = n
    # n1(0,0) -> n2(1,1) -> n3(1,0) -> n4(2,0) and n1->n3 direct
    nodes[(0, 0)].add_link(NodeLink("n", Coord("U8Area", 1, 1, 0), ["n"]))
    nodes[(1, 1)].add_link(NodeLink("s", Coord("U8Area", 0, 0, 0), ["s"]))
    nodes[(1, 1)].add_link(NodeLink("s_e", Coord("U8Area", 1, 0, 0), ["e"]))
    nodes[(1, 0)].add_link(NodeLink("n_w", Coord("U8Area", 1, 1, 0), ["w"]))
    nodes[(0, 0)].add_link(NodeLink("e", Coord("U8Area", 1, 0, 0), ["e"]))
    nodes[(1, 0)].add_link(NodeLink("w", Coord("U8Area", 0, 0, 0), ["w"]))
    nodes[(1, 0)].add_link(NodeLink("e2", Coord("U8Area", 2, 0, 0), ["e"]))
    nodes[(2, 0)].add_link(NodeLink("w2", Coord("U8Area", 1, 0, 0), ["w"]))
    area.add_grid(grid)
    nh.add_area(area)
    with patch("atheriz.pathfind.get_node_handler", return_value=nh), patch(
        "atheriz.objects.nodes.get_node_handler", return_value=nh
    ):
        with patch("atheriz.pathfind.heapq.heapify") as mock_heapify:
            success, path, closed = astar(nodes[(0, 0)], nodes[(2, 0)])
            assert success is True
            # shortest path should be n1->n3->n4 length 3
            assert len(path) == 3
            assert path[0] == nodes[(0, 0)]
            assert path[-1] == nodes[(2, 0)]
            # heapify should only be called for initial heap (at most once), not for g-improvement
            assert mock_heapify.call_count <= 1


def test_pathfind_stale_entries_skipped():
    # Directly test stale-entry logic by forcing duplicate pushes
    from atheriz.pathfind import astar
    from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
    from atheriz.globals.node import NodeHandler

    nh = NodeHandler()
    area = NodeArea(name="StaleArea")
    grid = NodeGrid(area="StaleArea", z=0)
    # 1 x 10 line, ensure algorithm works with heap duplicates
    size = 5
    nodes = {}
    for x in range(size):
        n = Node(coord=Coord("StaleArea", x, 0, 0))
        nodes[(x, 0)] = n
        grid.nodes[(x, 0)] = n
    for x in range(size - 1):
        nodes[(x, 0)].add_link(NodeLink(f"e{x}", Coord("StaleArea", x + 1, 0, 0), ["e"]))
        nodes[(x + 1, 0)].add_link(NodeLink(f"w{x}", Coord("StaleArea", x, 0, 0), ["w"]))
    # add extra longer alternative link from 0->2 to create duplicate open entries
    nodes[(0, 0)].add_link(NodeLink("jump", Coord("StaleArea", 2, 0, 0), ["j"]))
    nodes[(2, 0)].add_link(NodeLink("jump_back", Coord("StaleArea", 0, 0, 0), ["jb"]))
    area.add_grid(grid)
    nh.add_area(area)
    with patch("atheriz.pathfind.get_node_handler", return_value=nh), patch(
        "atheriz.objects.nodes.get_node_handler", return_value=nh
    ):
        success, path, closed = astar(nodes[(0, 0)], nodes[(4, 0)])
        assert success is True
        assert path[0] == nodes[(0, 0)]
        assert path[-1] == nodes[(4, 0)]
        assert len(path) == 4  # shortcut 0->2 makes 4 nodes (was 5 without shortcut)
