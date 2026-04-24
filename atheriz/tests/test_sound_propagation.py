import pytest

from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.objects.base_obj import Object
from atheriz.globals.get import get_node_handler
import atheriz.settings as settings

AREA = "bfs_sound_test"
ATTEN = settings.DEFAULT_OPEN_SOUND_ATTENUATION
GRID = 9


class TrackingNode(Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heard_sounds = []

    def at_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        self.heard_sounds.append((emitter, sound_desc, sound_msg, loudness, is_say))
        return super().at_hear(emitter, sound_desc, sound_msg, loudness, is_say)


class TrackingObject(Object):
    def __init__(self):
        super().__init__()
        self.heard_sounds = []

    def at_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        self.heard_sounds.append((emitter, sound_desc, sound_msg, loudness, is_say))


class BlockingNode(TrackingNode):
    def at_pre_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        return False, emitter, sound_desc, sound_msg, loudness, is_say


@pytest.fixture
def cube():
    nh = get_node_handler()
    area = NodeArea(name=AREA)
    for z in range(GRID):
        grid = NodeGrid(area=AREA, z=z)
        for x in range(GRID):
            for y in range(GRID):
                node = TrackingNode(coord=(AREA, x, y, z))
                grid.nodes[(x, y)] = node
        area.add_grid(grid)
    nh.add_area(area)
    return nh, area


def _place(nh, coord):
    node = nh.get_node(coord)
    emitter = TrackingObject.create(None, "Emitter", is_npc=True)
    emitter.location = node
    node._contents.add(emitter.id)
    return emitter, node


def _all_nodes(area):
    for z in range(GRID):
        grid = area.get_grid(z)
        if grid:
            for node in grid.nodes.values():
                yield node


def test_source_room_objects_hear_at_full_loudness(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)
    listener = TrackingObject.create(None, "Listener", is_npc=True)
    listener.location = center_node
    center_node._contents.add(listener.id)

    emitter.at_emit_sound("hello", "Hello!", 100.0, True)

    assert len(listener.heard_sounds) == 1
    assert listener.heard_sounds[0][3] == pytest.approx(100.0)
    assert listener.heard_sounds[0][4] is True
    assert emitter.heard_sounds[0][3] == pytest.approx(100.0)


def test_single_axis_hop_attenuation(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)

    emitter.at_emit_sound("bang", "bang!", 100.0, False)

    expected = 100.0 - ATTEN
    for hop, x in enumerate(range(5, 9), start=1):
        coord = (AREA, x, 4, 4)
        node = nh.get_node(coord)
        assert node.heard_sounds, f"Hop {hop} at {coord}: no sound received"
        actual = node.heard_sounds[0][3]
        assert actual == pytest.approx(expected, abs=0.01), (
            f"Hop {hop} at {coord}: expected {expected}, got {actual}"
        )
        expected -= ATTEN


def test_all_six_directions_propagate(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)

    emitter.at_emit_sound("bang", "bang!", 100.0, False)

    directions = [
        (AREA, 5, 4, 4),
        (AREA, 3, 4, 4),
        (AREA, 4, 5, 4),
        (AREA, 4, 3, 4),
        (AREA, 4, 4, 5),
        (AREA, 4, 4, 3),
    ]
    expected_loudness = 100.0 - ATTEN
    for coord in directions:
        node = nh.get_node(coord)
        assert node.heard_sounds, f"{coord}: no sound received"
        actual = node.heard_sounds[0][3]
        assert actual == pytest.approx(expected_loudness, abs=0.01), (
            f"{coord}: expected {expected_loudness}, got {actual}"
        )


def test_diagonal_node_attenuation(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)

    emitter.at_emit_sound("bang", "bang!", 100.0, False)

    diagonal = (AREA, 5, 5, 4)
    node = nh.get_node(diagonal)
    assert node.heard_sounds, f"{diagonal}: no sound received"
    actual = node.heard_sounds[0][3]
    expected = 100.0 - 2 * ATTEN
    assert actual == pytest.approx(expected, abs=0.01), (
        f"{diagonal}: expected {expected} (2 BFS hops), got {actual}"
    )


def test_node_hears_once(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)

    emitter.at_emit_sound("bang", "bang!", 100.0, False)

    errors = []
    for node in _all_nodes(area):
        if len(node.heard_sounds) > 1:
            errors.append(f"{node.coord}: heard {len(node.heard_sounds)} times")
    assert not errors, f"Nodes heard more than once:\n" + "\n".join(errors)


def test_sound_stops_at_zero_loudness(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)
    loudness = 30.0

    emitter.at_emit_sound("tap", "tap.", loudness, False)

    near = (AREA, 5, 4, 4)
    near_node = nh.get_node(near)
    assert near_node.heard_sounds, "1-hop neighbor should hear"

    far = (AREA, 7, 4, 4)
    far_node = nh.get_node(far)
    assert not far_node.heard_sounds, "3-hop node should not hear with loudness 30"


def test_blocking_node_skips_contents_but_propagates():
    nh = get_node_handler()
    area = NodeArea(name="bfs_block_test")
    grid = NodeGrid(area="bfs_block_test", z=0)
    source = TrackingNode(coord=("bfs_block_test", 0, 0, 0))
    blocker = BlockingNode(coord=("bfs_block_test", 1, 0, 0))
    beyond = TrackingNode(coord=("bfs_block_test", 2, 0, 0))
    grid.nodes[(0, 0)] = source
    grid.nodes[(1, 0)] = blocker
    grid.nodes[(2, 0)] = beyond
    area.add_grid(grid)
    nh.add_area(area)

    emitter = TrackingObject.create(None, "Emitter", is_npc=True)
    emitter.location = source
    source._contents.add(emitter.id)

    obj_in_blocker = TrackingObject.create(None, "Inside", is_npc=True)
    obj_in_blocker.location = blocker
    blocker._contents.add(obj_in_blocker.id)

    obj_in_beyond = TrackingObject.create(None, "Beyond", is_npc=True)
    obj_in_beyond.location = beyond
    beyond._contents.add(obj_in_beyond.id)

    emitter.at_emit_sound("bang", "bang!", 100.0, False)

    assert len(blocker.heard_sounds) == 1, "Blocking node's at_hear should be called"
    assert blocker.heard_sounds[0][3] == pytest.approx(90.0)
    assert len(obj_in_blocker.heard_sounds) == 0, "Object inside blocking node should not hear"
    assert len(beyond.heard_sounds) == 1, "Sound should pass through blocking node"
    assert beyond.heard_sounds[0][3] == pytest.approx(80.0)
    assert len(obj_in_beyond.heard_sounds) == 1, "Object beyond blocker should hear"
    assert obj_in_beyond.heard_sounds[0][3] == pytest.approx(80.0)


def test_empty_message_no_propagation(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)
    listener = TrackingObject.create(None, "L", is_npc=True)
    listener.location = center_node
    center_node._contents.add(listener.id)

    emitter.at_emit_sound("desc", "", 100.0, False)

    assert len(listener.heard_sounds) == 0
    for node in _all_nodes(area):
        assert len(node.heard_sounds) == 0

    emitter.at_emit_sound("desc", None, 100.0, False)

    assert len(listener.heard_sounds) == 0


def test_no_location_no_propagation():
    emitter = TrackingObject.create(None, "Float", is_npc=True)
    emitter.at_emit_sound("desc", "msg", 100.0, False)
