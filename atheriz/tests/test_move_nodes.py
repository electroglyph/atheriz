from threading import RLock

from atheriz.objects.base_door import Door
from atheriz.objects.nodes import Node, NodeGrid, NodeLink
from atheriz.utils import Coord


class FakeNodeHandler:
    def __init__(self):
        self.doors = {}
        self.transitions = {}
        self.lock3 = RLock()
        self.lock2 = RLock()

    def add_transition(self, transition):
        with self.lock2:
            self.transitions[transition.to_coord] = transition

    def remove_transition(self, destination):
        with self.lock2:
            self.transitions.pop(destination, None)


def make_grid(*nodes) -> tuple[NodeGrid, FakeNodeHandler]:
    grid = NodeGrid("TestArea", 0)
    nh = FakeNodeHandler()
    for n in nodes:
        grid.nodes[(n.coord.x, n.coord.y)] = n
    return grid, nh


def test_check_moves_denies_occupied_destination():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, _ = make_grid(a, b)
    failed = grid.check_moves([((0, 0), (1, 0))])
    assert failed == {0}


def test_check_moves_allows_free_destination():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    grid, _ = make_grid(a)
    assert grid.check_moves([((0, 0), (5, 5))]) == set()


def test_apply_moves_rekeys_node_and_inbound_links():
    a = Node(coord=Coord("TestArea", 0, 0, 0), desc="A")
    b = Node(coord=Coord("TestArea", 1, 0, 0), desc="B")
    # B's link points at A's coord: must follow A to its new position
    b.links.append(NodeLink(name="West", coord=Coord("TestArea", 0, 0, 0)))
    grid, _ = make_grid(a, b)

    failed = grid.apply_moves([((0, 0), (5, 0))])
    assert failed == []
    assert grid.get_node((0, 0)) is None
    moved = grid.get_node((5, 0))
    assert moved is a
    assert moved.coord == Coord("TestArea", 5, 0, 0)
    assert b.links[0].coord == Coord("TestArea", 5, 0, 0)


def test_apply_moves_supports_swap():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    a.links.append(NodeLink(name="East", coord=Coord("TestArea", 1, 0, 0)))
    b.links.append(NodeLink(name="West", coord=Coord("TestArea", 0, 0, 0)))
    grid, _ = make_grid(a, b)

    failed = grid.apply_moves([((0, 0), (1, 0)), ((1, 0), (0, 0))])
    assert failed == []
    assert grid.get_node((1, 0)) is a
    assert grid.get_node((0, 0)) is b
    assert a.links[0].coord == Coord("TestArea", 0, 0, 0)
    assert b.links[0].coord == Coord("TestArea", 1, 0, 0)


def test_apply_moves_supports_chains():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, _ = make_grid(a, b)

    failed = grid.apply_moves([((0, 0), (1, 0)), ((1, 0), (2, 0))])
    assert failed == []
    assert grid.get_node((1, 0)) is a
    assert grid.get_node((2, 0)) is b


def test_apply_moves_reports_failed_indices_without_touching_them():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    c = Node(coord=Coord("TestArea", 2, 0, 0))
    grid, _ = make_grid(a, b, c)

    # index 1 is invalid: destination (2,0) is occupied and not being vacated
    failed = grid.apply_moves([((0, 0), (5, 0)), ((1, 0), (2, 0))])
    assert failed == [1]
    assert grid.get_node((1, 0)) is b
    assert grid.get_node((2, 0)) is c
    assert grid.get_node((5, 0)) is a


def test_apply_moves_rekeys_doors():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, nh = make_grid(a, b)
    door = Door(
        from_coord=Coord("TestArea", 0, 0, 0),
        from_exit="East",
        to_coord=Coord("TestArea", 1, 0, 0),
        to_exit="West",
        symbol_coord=(0, 0),
    )
    nh.doors[door.from_coord] = {"East": door}
    nh.doors[door.to_coord] = {"West": door}

    import atheriz.objects.nodes as nodes_module

    original = nodes_module.get_node_handler
    nodes_module.get_node_handler = lambda: nh
    try:
        failed = grid.apply_moves([((0, 0), (4, 0))])
    finally:
        nodes_module.get_node_handler = original

    assert failed == []
    new_full = Coord("TestArea", 4, 0, 0)
    assert nh.doors.get(Coord("TestArea", 0, 0, 0)) is None
    assert nh.doors[new_full]["East"] is door
    assert nh.doors[Coord("TestArea", 1, 0, 0)]["West"] is door
    assert door.from_coord == new_full
    assert door.to_coord == Coord("TestArea", 1, 0, 0)


def test_apply_moves_refreshes_cross_area_transitions():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    a.links.append(NodeLink(name="Portal", coord=Coord("OtherArea", 0, 0, 0)))
    grid, nh = make_grid(a)

    import atheriz.objects.nodes as nodes_module

    original = nodes_module.get_node_handler
    nodes_module.get_node_handler = lambda: nh
    try:
        grid.apply_moves([((0, 0), (3, 0))])
    finally:
        nodes_module.get_node_handler = original

    t = nh.transitions.get(Coord("OtherArea", 0, 0, 0))
    assert t is not None
    assert t.from_coord == Coord("TestArea", 3, 0, 0)


# ==================== ExitCommand rebuild tests ====================


class FakeCmdset:
    def __init__(self):
        self.removed_tags = []
        self.added = []

    def remove_by_tag(self, tag):
        self.removed_tags.append(tag)

    def adds(self, cmds):
        self.added.extend(cmds)


class FakeObj:
    def __init__(self, id):
        self.id = id
        self.internal_cmdset = FakeCmdset()


def test_apply_moves_rebuilds_exits_for_moved_room_contents():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    a.links.append(NodeLink(name="East", coord=Coord("TestArea", 1, 0, 0)))
    grid, nh = make_grid(a)
    occupant = FakeObj(101)
    a._contents = {101}

    import atheriz.objects.nodes as nodes_module

    original_nh = nodes_module.get_node_handler
    original_get = nodes_module.get
    nodes_module.get_node_handler = lambda: nh
    nodes_module.get = lambda ids: [occupant] if 101 in ids else []
    try:
        failed = grid.apply_moves([((0, 0), (5, 0))])
    finally:
        nodes_module.get_node_handler = original_nh
        nodes_module.get = original_get

    assert failed == []
    assert occupant.internal_cmdset.removed_tags == ["exits"]
    assert len(occupant.internal_cmdset.added) == 1
    ec = occupant.internal_cmdset.added[0]
    assert ec.location == Coord("TestArea", 5, 0, 0)
    assert ec.destination == Coord("TestArea", 1, 0, 0)


def test_apply_moves_rebuilds_exits_for_neighbor_contents():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    # B's inbound link points at A: must be rewritten, then B's occupants'
    # exit commands must get A's new coord as their destination
    b.links.append(NodeLink(name="West", coord=Coord("TestArea", 0, 0, 0)))
    grid, nh = make_grid(a, b)
    neighbor_occupant = FakeObj(202)
    b._contents = {202}

    import atheriz.objects.nodes as nodes_module

    original_nh = nodes_module.get_node_handler
    original_get = nodes_module.get
    nodes_module.get_node_handler = lambda: nh
    nodes_module.get = lambda ids: [neighbor_occupant] if 202 in ids else []
    try:
        failed = grid.apply_moves([((0, 0), (7, 0))])
    finally:
        nodes_module.get_node_handler = original_nh
        nodes_module.get = original_get

    assert failed == []
    assert neighbor_occupant.internal_cmdset.removed_tags == ["exits"]
    assert len(neighbor_occupant.internal_cmdset.added) == 1
    ec = neighbor_occupant.internal_cmdset.added[0]
    assert ec.location == Coord("TestArea", 1, 0, 0)
    assert ec.destination == Coord("TestArea", 7, 0, 0)
    assert ec.key == "West"


# ==================== check_moves context (pending unsaved moves) ====================


def test_check_moves_context_allows_context_vacated_destination():
    # A sits at (0,0) on the server; the editor has a PENDING unsaved move
    # A:(0,0)->(5,0). A new drag B:(1,0)->(0,0) targets the coordinate A is
    # about to vacate and must NOT be denied.
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, _ = make_grid(a, b)
    failed = grid.check_moves(
        [((1, 0), (0, 0))],
        context=[((0, 0), (5, 0))],
    )
    assert failed == set()


def test_check_moves_context_still_denies_genuine_collision():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, _ = make_grid(a, b)
    # unrelated pending move that does not free the destination
    failed = grid.check_moves([((1, 0), (0, 0))], context=[((9, 9), (8, 8))])
    assert failed == {0}
    # no context at all behaves as before
    assert grid.check_moves([((1, 0), (0, 0))]) == {0}


def test_check_moves_context_does_not_make_source_available():
    # if the context moves a room AWAY from src, a new move from src is
    # invalid because by save time src will be empty
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, _ = make_grid(a, b)
    failed = grid.check_moves([((0, 0), (5, 5))], context=[((0, 0), (3, 3))])
    assert failed == {0}


def test_check_moves_context_honors_new_move_vacated_sources():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    c = Node(coord=Coord("TestArea", 2, 0, 0))
    grid, _ = make_grid(a, b, c)
    # chain across batch + context: (0,0)->(1,0) allowed because the batch
    # itself vacates (1,0), whose occupant moves to (2,0)... which is
    # occupied, so instead verify swap+context combined
    failed = grid.check_moves(
        [((0, 0), (1, 0)), ((1, 0), (0, 0))],
        context=[((2, 0), (9, 9))],
    )
    assert failed == set()


def test_apply_moves_ignores_context_and_applies_in_order():
    a = Node(coord=Coord("TestArea", 0, 0, 0))
    b = Node(coord=Coord("TestArea", 1, 0, 0))
    grid, _ = make_grid(a, b)
    # save-time application has no context; pendings apply sequentially
    failed = grid.apply_moves([((0, 0), (1, 0)), ((1, 0), (0, 0))])
    assert failed == []
    assert grid.get_node((1, 0)) is a
    assert grid.get_node((0, 0)) is b
