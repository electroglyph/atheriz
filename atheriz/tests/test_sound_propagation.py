import math
from math import gcd

import pytest

from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.objects.base_obj import Object
from atheriz.globals.get import get_node_handler
import atheriz.settings as settings

AREA = "sound_test"
ATTEN = settings.DEFAULT_OPEN_SOUND_ATTENUATION
GRID = 9


class TrackingNode(Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.heard_sounds = []

    def at_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        self.heard_sounds.append((emitter, sound_desc, sound_msg, loudness, is_say))
        return super().at_hear(emitter, sound_desc, sound_msg, loudness, is_say)


class TrackingPCObject(Object):
    def __init__(self):
        super().__init__()
        self.heard_sounds = []

    def at_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        self.heard_sounds.append((emitter, sound_desc, sound_msg, loudness, is_say))


class TrackingObject(Object):
    def __init__(self):
        super().__init__()
        self.heard_sounds = []

    def at_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        self.heard_sounds.append((emitter, sound_desc, sound_msg, loudness, is_say))


class BlockingNode(TrackingNode):
    def at_pre_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        return False, emitter, sound_desc, sound_msg, loudness, is_say


class BlockingEmitterObject(TrackingObject):
    def at_pre_emit_sound(self, emitter, sound_desc, sound_msg, loudness, is_say):
        return False, emitter, sound_desc, sound_msg, loudness, is_say


class BlockingRoomObject(TrackingObject):
    def at_pre_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        return False, emitter, sound_desc, sound_msg, loudness, is_say


class PreHearCountingNode(TrackingNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pre_hear_calls = 0

    def at_pre_hear(self, emitter, sound_desc, sound_msg, loudness, is_say):
        self.pre_hear_calls += 1
        return super().at_pre_hear(emitter, sound_desc, sound_msg, loudness, is_say)


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


def _hop(c1, c2):
    dx = abs(c2[1] - c1[1])
    dy = abs(c2[2] - c1[2])
    dz = abs(c2[3] - c1[3])
    if dx == 0 and dy == 0 and dz == 0:
        return 0
    return gcd(gcd(dx, dy), dz)


def _dist(c1, c2):
    dx = c2[1] - c1[1]
    dy = c2[2] - c1[2]
    dz = c2[3] - c1[3]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _expected_loudness(original, hop):
    return original - hop * ATTEN


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


# ==================== Center Emission ====================


def test_center_emission_all_nodes_hear(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)
    emitter.at_emit_sound("bang", "A loud bang!", 100.0, False)

    heard = [n for n in _all_nodes(area) if n.heard_sounds]
    assert len(heard) == GRID**3 - 1
    assert len(center_node.heard_sounds) == 0


def test_center_emission_loudness_tapering(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)
    loudness = 100.0
    emitter.at_emit_sound("bang", "A loud bang!", loudness, False)

    errors = []
    for node in _all_nodes(area):
        if node.coord == center:
            continue
        if not node.heard_sounds:
            errors.append(f"{node.coord}: no sound received")
            continue
        hop = _hop(center, node.coord)
        expected = _expected_loudness(loudness, hop)
        actual = node.heard_sounds[0][3]
        if actual != pytest.approx(expected, abs=0.01):
            errors.append(f"{node.coord}: expected {expected}, got {actual}")

    assert not errors, f"{len(errors)} failures:\n" + "\n".join(errors[:10])


def test_single_ray_loudness_reduces_per_hop(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)
    original = 100.0
    emitter.at_emit_sound("bang", "bang!", original, False)

    expected = original - ATTEN
    for hop, x in enumerate(range(5, 9), start=1):
        coord = (AREA, x, 4, 4)
        node = nh.get_node(coord)
        assert node.heard_sounds, f"Hop {hop} at {coord}: no sound received"
        actual = node.heard_sounds[0][3]
        assert actual == pytest.approx(expected, abs=0.01), (
            f"Hop {hop} at {coord}: expected {expected}, got {actual}"
        )
        expected -= ATTEN


def test_center_emission_axis_ray(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)
    loudness = 100.0
    emitter.at_emit_sound("bang", "bang!", loudness, False)

    expected_axis = {
        (AREA, 5, 4, 4): 90.0,
        (AREA, 6, 4, 4): 80.0,
        (AREA, 7, 4, 4): 70.0,
        (AREA, 8, 4, 4): 60.0,
        (AREA, 3, 4, 4): 90.0,
        (AREA, 2, 4, 4): 80.0,
        (AREA, 1, 4, 4): 70.0,
        (AREA, 0, 4, 4): 60.0,
    }
    for coord, exp in expected_axis.items():
        node = nh.get_node(coord)
        assert node.heard_sounds, f"{coord} heard nothing"
        assert node.heard_sounds[0][3] == pytest.approx(exp, abs=0.01), (
            f"{coord}: expected {exp}, got {node.heard_sounds[0][3]}"
        )


def test_center_emission_diagonal_ray(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)
    loudness = 100.0
    emitter.at_emit_sound("bang", "bang!", loudness, False)

    expected_diag = {
        (AREA, 5, 5, 5): 90.0,
        (AREA, 6, 6, 6): 80.0,
        (AREA, 7, 7, 7): 70.0,
        (AREA, 8, 8, 8): 60.0,
    }
    for coord, exp in expected_diag.items():
        node = nh.get_node(coord)
        assert node.heard_sounds, f"{coord} heard nothing"
        assert node.heard_sounds[0][3] == pytest.approx(exp, abs=0.01)


def test_center_emission_fields_preserved(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)
    emitter.at_emit_sound("test_desc", "test_msg", 100.0, True)

    for node in _all_nodes(area):
        if node.coord == center or not node.heard_sounds:
            continue
        e, s_desc, s_msg, loud, is_s = node.heard_sounds[0]
        assert e is emitter, f"{node.coord}: wrong emitter"
        assert s_desc == "test_desc", f"{node.coord}: wrong sound_desc"
        assert s_msg == "test_msg", f"{node.coord}: wrong sound_msg"
        assert is_s is True, f"{node.coord}: wrong is_say"


# ==================== Corner Emission ====================


def test_corner_emission_within_radius_hear(cube):
    nh, area = cube
    corner = (AREA, 0, 0, 0)
    emitter, corner_node = _place(nh, corner)
    loudness = 50.0
    post_source = loudness - ATTEN
    radius = post_source / ATTEN

    emitter.at_emit_sound("tap", "tap.", loudness, False)

    beyond_heard = []
    within_silent = []
    for node in _all_nodes(area):
        if node.coord == corner:
            continue
        d = _dist(corner, node.coord)
        if node.heard_sounds and d > radius + 0.01:
            beyond_heard.append((node.coord, d))
        if not node.heard_sounds and d <= radius + 0.01:
            within_silent.append((node.coord, d))

    assert not beyond_heard, f"Nodes beyond radius heard: {beyond_heard[:5]}"
    assert not within_silent, f"Nodes within radius silent: {within_silent[:5]}"
    assert len(corner_node.heard_sounds) == 0


def test_corner_emission_loudness_tapering(cube):
    nh, area = cube
    corner = (AREA, 0, 0, 0)
    emitter, _ = _place(nh, corner)
    loudness = 50.0
    post_source = loudness - ATTEN
    radius = post_source / ATTEN

    emitter.at_emit_sound("tap", "tap.", loudness, False)

    errors = []
    for node in _all_nodes(area):
        if node.coord == corner:
            continue
        d = _dist(corner, node.coord)
        if d > radius + 0.01:
            continue
        if not node.heard_sounds:
            errors.append(f"{node.coord} (d={d:.2f}): no sound")
            continue
        hop = _hop(corner, node.coord)
        expected = _expected_loudness(loudness, hop)
        actual = node.heard_sounds[0][3]
        if actual != pytest.approx(expected, abs=0.01):
            errors.append(f"{node.coord}: expected {expected}, got {actual}")

    assert not errors, f"{len(errors)} failures:\n" + "\n".join(errors[:10])


def test_corner_emission_far_nodes_silent(cube):
    nh, area = cube
    corner = (AREA, 0, 0, 0)
    emitter, _ = _place(nh, corner, )
    emitter.at_emit_sound("tap", "tap.", 30.0, False)
    # post_source = 20, radius = 2.0

    far = (AREA, 3, 0, 0)
    far_node = nh.get_node(far)
    assert not far_node.heard_sounds, "Node at distance 3 should not hear (radius=2.0)"


# ==================== Object Hearing ====================


def test_source_room_objects_hear_at_full_loudness(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)
    listener = TrackingObject.create(None, "Listener", is_npc=True)
    listener.location = center_node
    center_node._contents.add(listener.id)

    emitter.at_emit_sound("hello", "Hello!", 100.0, True)

    assert len(emitter.heard_sounds) == 1
    assert emitter.heard_sounds[0][3] == pytest.approx(100.0)
    assert emitter.heard_sounds[0][4] is True

    assert len(listener.heard_sounds) == 1
    assert listener.heard_sounds[0][3] == pytest.approx(100.0)
    assert listener.heard_sounds[0][2] == "Hello!"


def test_remote_room_objects_hear_at_attenuated_loudness(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)

    remote = (AREA, 6, 4, 4)
    remote_node = nh.get_node(remote)
    listener = TrackingObject.create(None, "RemoteListener", is_npc=True)
    listener.location = remote_node
    remote_node._contents.add(listener.id)

    emitter.at_emit_sound("shout", "A shout!", 100.0, False)

    assert len(listener.heard_sounds) == 1
    expected = _expected_loudness(100.0, 2)
    assert listener.heard_sounds[0][3] == pytest.approx(expected)


def test_beyond_range_objects_dont_hear(cube):
    nh, area = cube
    corner = (AREA, 0, 0, 0)
    emitter, _ = _place(nh, corner)

    far = (AREA, 3, 0, 0)
    far_node = nh.get_node(far)
    listener = TrackingObject.create(None, "FarListener", is_npc=True)
    listener.location = far_node
    far_node._contents.add(listener.id)

    emitter.at_emit_sound("whisper", "psst", 30.0, False)

    assert len(listener.heard_sounds) == 0


def test_non_hearing_object_ignored(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)
    deaf = TrackingObject.create(None, "Deaf")
    deaf.location = center_node
    center_node._contents.add(deaf.id)

    emitter.at_emit_sound("hello", "Hello!", 100.0, False)

    assert len(deaf.heard_sounds) == 0


# ==================== Blocking ====================


def test_at_pre_emit_sound_blocks_emission(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    node = nh.get_node(center)

    emitter = BlockingEmitterObject.create(None, "Mute", is_npc=True)
    emitter.location = node
    node._contents.add(emitter.id)

    emitter.at_emit_sound("bang", "bang!", 100.0, False)

    for n in _all_nodes(area):
        assert len(n.heard_sounds) == 0, f"{n.coord} should not have heard"
    assert len(emitter.heard_sounds) == 0


def test_node_at_pre_hear_skips_contents_but_continues_ray():
    nh = get_node_handler()
    area = NodeArea(name="block_test")
    grid = NodeGrid(area="block_test", z=0)
    source = TrackingNode(coord=("block_test", 0, 0, 0))
    blocker = BlockingNode(coord=("block_test", 1, 0, 0))
    beyond = TrackingNode(coord=("block_test", 2, 0, 0))
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

    assert len(blocker.heard_sounds) == 1, "Blocking node's at_hear is called"
    assert blocker.heard_sounds[0][3] == pytest.approx(90.0)
    assert len(obj_in_blocker.heard_sounds) == 0, "Object inside blocking node should not hear"
    assert len(beyond.heard_sounds) == 1, "Sound should pass through blocking node"
    assert beyond.heard_sounds[0][3] == pytest.approx(80.0)
    assert len(obj_in_beyond.heard_sounds) == 1, "Object beyond blocker should hear"
    assert obj_in_beyond.heard_sounds[0][3] == pytest.approx(80.0)


def test_object_at_pre_hear_blocks_hearing(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)

    blocker = BlockingRoomObject.create(None, "Blocker", is_npc=True)
    blocker.location = center_node
    center_node._contents.add(blocker.id)

    emitter.at_emit_sound("hello", "Hello!", 100.0, False)

    assert len(blocker.heard_sounds) == 0, "Object with at_pre_hear=False should not hear"
    assert len(emitter.heard_sounds) == 1, "Emitter should still hear itself"


# ==================== Edge Cases ====================


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


def test_none_message_no_propagation(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)
    listener = TrackingObject.create(None, "L", is_npc=True)
    listener.location = center_node
    center_node._contents.add(listener.id)

    emitter.at_emit_sound("desc", None, 100.0, False)

    assert len(listener.heard_sounds) == 0


def test_no_location_no_propagation():
    emitter = TrackingObject.create(None, "Float", is_npc=True)
    emitter.at_emit_sound("desc", "msg", 100.0, False)


# ==================== Bug Detection ====================


def test_at_pre_hear_called_once_per_remote_node():
    nh = get_node_handler()
    area = NodeArea(name="prehear_count")
    grid = NodeGrid(area="prehear_count", z=0)
    source = PreHearCountingNode(coord=("prehear_count", 0, 0, 0))
    remote = PreHearCountingNode(coord=("prehear_count", 1, 0, 0))
    grid.nodes[(0, 0)] = source
    grid.nodes[(1, 0)] = remote
    area.add_grid(grid)
    nh.add_area(area)

    emitter = TrackingObject.create(None, "E", is_npc=True)
    emitter.location = source
    source._contents.add(emitter.id)

    emitter.at_emit_sound("t", "m", 100.0, False)

    assert remote.pre_hear_calls == 1, (
        f"Expected at_pre_hear called once on remote node, got {remote.pre_hear_calls}. "
        "Node.at_pre_hear is called both from the ray loop in at_emit_sound AND "
        "inside Node.at_hear — double invocation is a bug."
    )


def test_pc_can_hear_sound_in_same_room(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)

    pc = TrackingPCObject.create(None, "TestPC", is_pc=True)
    pc.location = center_node
    center_node._contents.add(pc.id)

    emitter.at_emit_sound("bang", "A loud bang!", 100.0, False)

    assert len(pc.heard_sounds) == 1
    assert pc.heard_sounds[0][2] == "A loud bang!"
    assert pc.heard_sounds[0][3] == pytest.approx(100.0)


def test_pc_can_hear_sound_in_remote_room(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, _ = _place(nh, center)

    remote = (AREA, 6, 4, 4)
    remote_node = nh.get_node(remote)
    pc = TrackingPCObject.create(None, "TestPC", is_pc=True)
    pc.location = remote_node
    remote_node._contents.add(pc.id)

    emitter.at_emit_sound("shout", "A shout!", 100.0, False)

    assert len(pc.heard_sounds) == 1
    expected = _expected_loudness(100.0, 2)
    assert pc.heard_sounds[0][3] == pytest.approx(expected)


def test_pc_cannot_hear_without_can_hear(cube):
    nh, area = cube
    center = (AREA, 4, 4, 4)
    emitter, center_node = _place(nh, center)

    pc = TrackingPCObject.create(None, "DeafPC", is_pc=True)
    pc.can_hear = False
    pc.location = center_node
    center_node._contents.add(pc.id)

    emitter.at_emit_sound("bang", "A loud bang!", 100.0, False)

    assert len(pc.heard_sounds) == 0
