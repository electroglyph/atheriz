import pytest
from unittest.mock import patch

from atheriz import settings
from atheriz.commands.loggedin.mapedit import DrawCommand
from atheriz.globals import mapedit
from atheriz.globals.map import MapInfo
from atheriz.inputfuncs import InputFuncs
from atheriz.objects.nodes import Node, NodeLink
from atheriz.tests.fakes import FakeConnection, FakeSession
from atheriz.utils import Coord


@pytest.fixture(autouse=True)
def clear_chains():
    mapedit._chains.clear()
    yield
    mapedit._chains.clear()


class MockMapHandler:
    def __init__(self):
        self.data = {}

    def get_mapinfo(self, area, z):
        return self.data.get((area, z))

    def set_mapinfo(self, area, z, mi):
        self.data[(area, z)] = mi


class MockCaller:
    def __init__(self, location=None, conn=None, is_builder=True):
        self.location = location
        self.is_builder = is_builder
        self.messages = []
        self.session = FakeSession()
        if conn is not None:
            self.session.connection = conn

    def msg(self, text=None, **kwargs):
        self.messages.append(text)


def make_conn(ip="10.0.0.1"):
    conn = FakeConnection()
    conn.client_host = ip
    return conn


def make_mi(grid=None):
    mi = MapInfo(name="TestArea")
    if grid:
        for coord, symbol in grid.items():
            mi.pre_grid[coord] = symbol
    return mi


# ==================== Key chain unit tests ====================


def test_grant_returns_unique_keys():
    k1 = mapedit.grant("10.0.0.1", "TestArea", 0)
    k2 = mapedit.grant("10.0.0.1", "TestArea", 0)
    assert k1 and k2
    assert k1 != k2
    assert len(k1) > 16


def test_consume_unknown_key():
    result = mapedit.consume("bogus", "10.0.0.1", 0)
    assert result.status == mapedit.REJECT
    assert result.reason == "unknown_key"


def test_consume_handshake_rotates_key():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    result = mapedit.consume(key, "10.0.0.1", 0)
    assert result.status == mapedit.PROCESSED
    assert result.new_key != key
    assert result.chain.seq == 0
    assert result.chain.area == "TestArea"
    assert result.chain.z == 0


def test_consume_edit_then_retry():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    handshake = mapedit.consume(key, "10.0.0.1", 0)
    assert handshake.status == mapedit.PROCESSED
    key_after_handshake = handshake.new_key

    edit = mapedit.consume(key_after_handshake, "10.0.0.1", 1)
    assert edit.status == mapedit.PROCESSED
    assert edit.chain.seq == 1
    key_after_edit = edit.new_key

    retry = mapedit.consume(key_after_handshake, "10.0.0.1", 1)
    assert retry.status == mapedit.RETRY
    assert retry.new_key == key_after_edit
    assert retry.chain.seq == 1


def test_consume_replay():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    handshake = mapedit.consume(key, "10.0.0.1", 0)
    current = mapedit.consume(handshake.new_key, "10.0.0.1", 0)
    assert current.status == mapedit.REJECT
    assert current.reason == "replay"


def test_consume_gap():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    handshake = mapedit.consume(key, "10.0.0.1", 0)
    result = mapedit.consume(handshake.new_key, "10.0.0.1", 5)
    assert result.status == mapedit.REJECT
    assert result.reason == "gap"


def test_consume_wrong_ip():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    result = mapedit.consume(key, "10.0.0.2", 0)
    assert result.status == mapedit.REJECT
    assert result.reason == "ip"


def test_consume_old_key_after_rotation_is_stale():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    handshake = mapedit.consume(key, "10.0.0.1", 0)
    mapedit.consume(handshake.new_key, "10.0.0.1", 1)
    result = mapedit.consume(key, "10.0.0.1", 0)
    assert result.status == mapedit.REJECT
    assert result.reason == "unknown_key"


def test_consume_previous_key_with_wrong_seq_is_replay():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    handshake = mapedit.consume(key, "10.0.0.1", 0)
    edit = mapedit.consume(handshake.new_key, "10.0.0.1", 1)
    assert edit.status == mapedit.PROCESSED
    assert edit.chain.seq == 1

    wrong_seq = mapedit.consume(handshake.new_key, "10.0.0.1", 5)
    assert wrong_seq.status == mapedit.REJECT
    assert wrong_seq.reason == "replay"

    retry = mapedit.consume(handshake.new_key, "10.0.0.1", 1)
    assert retry.status == mapedit.RETRY
    assert retry.new_key == edit.new_key


# ==================== Command tests ====================


def test_access_builder():
    caller = MockCaller(is_builder=True)
    assert DrawCommand().access(caller) is True


def test_access_non_builder():
    caller = MockCaller(is_builder=False)
    assert DrawCommand().access(caller) is False


def test_run_sends_launch_draw_with_payload():
    mi = make_mi({(0, 0): "X", (5, -2): "Y"})
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    node = Node(coord=Coord("TestArea", 3, 7, 0))
    conn = make_conn()
    caller = MockCaller(location=node, conn=conn)
    with patch("atheriz.commands.loggedin.mapedit.get_map_handler", return_value=mh):
        DrawCommand().run(caller, None)

    assert len(conn.sent) == 1
    cmd, args, _ = conn.sent[0]
    assert cmd == "launch_draw"
    key, payload = args[0], args[1]
    assert key
    assert payload["area"] == "TestArea"
    assert payload["z"] == 0
    assert set(tuple(c) for c in payload["grid"]) == {(0, 0, "X"), (5, -2, "Y")}
    assert payload["rooms"] == []
    assert caller.messages == ["Opening AtheriZ Draw in a new tab."]
    chain = mapedit.consume(key, "10.0.0.1", 0)
    assert chain.status == mapedit.PROCESSED


def test_run_sends_room_data():
    mi = make_mi({(0, 0): settings.ROOM_PLACEHOLDER, (5, -2): "Y"})
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    room = Node(coord=Coord("TestArea", 0, 0, 0))
    room.desc = "A dusty hall."
    room.links.append(NodeLink(name="North", coord=Coord("TestArea", 0, 1, 0), aliases=["n"]))
    room.links.append(NodeLink(name="East", coord=Coord("TestArea", 1, 0, 0)))
    room.links.append(NodeLink(name="Broken", coord=None))

    class MockNodeGrid:
        def get_node(self, coord):
            return room if coord == (0, 0) else None

    class MockNodeArea:
        def get_grid(self, z):
            return MockNodeGrid()

    class MockNodeHandler:
        def get_area(self, name):
            return MockNodeArea()

    node = Node(coord=Coord("TestArea", 3, 7, 0))
    conn = make_conn()
    caller = MockCaller(location=node, conn=conn)
    with patch("atheriz.commands.loggedin.mapedit.get_map_handler", return_value=mh), patch(
        "atheriz.commands.loggedin.mapedit.get_node_handler", return_value=MockNodeHandler()
    ):
        DrawCommand().run(caller, None)

    payload = conn.sent[0][1][1]
    assert payload["rooms"] == [
        {
            "x": 0,
            "y": 0,
            "desc": "A dusty hall.",
            "exits": [
                {"name": "North", "aliases": ["n"], "coord": ["TestArea", 0, 1, 0]},
                {"name": "East", "aliases": [], "coord": ["TestArea", 1, 0, 0]},
            ],
        }
    ]


def test_run_sends_rendered_symbols():
    mi = make_mi({(0, 0): settings.SINGLE_WALL_PLACEHOLDER})
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    node = Node(coord=Coord("TestArea", 3, 7, 0))
    conn = make_conn()
    caller = MockCaller(location=node, conn=conn)
    with patch("atheriz.commands.loggedin.mapedit.get_map_handler", return_value=mh):
        DrawCommand().run(caller, None)

    payload = conn.sent[0][1][1]
    assert payload["grid"] == [[0, 0, "─"]]


def test_run_preserves_post_grid_when_pre_grid_empty():
    mi = MapInfo(name="TestArea")
    mi.post_grid[(0, 0)] = "╬"
    mi.post_grid[(1, 0)] = "═"
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    node = Node(coord=Coord("TestArea", 3, 7, 0))
    conn = make_conn()
    caller = MockCaller(location=node, conn=conn)
    with patch("atheriz.commands.loggedin.mapedit.get_map_handler", return_value=mh):
        DrawCommand().run(caller, None)

    payload = conn.sent[0][1][1]
    assert set(tuple(c) for c in payload["grid"]) == {(0, 0, "╬"), (1, 0, "═")}
    assert mi.post_grid[(0, 0)] == "╬"


def test_run_creates_mapinfo_when_missing():
    mh = MockMapHandler()
    node = Node(coord=Coord("TestArea", 0, 0, 0))
    conn = make_conn()
    caller = MockCaller(location=node, conn=conn)
    with patch("atheriz.commands.loggedin.mapedit.get_map_handler", return_value=mh):
        DrawCommand().run(caller, None)
    assert mh.data[("TestArea", 0)].pre_grid == {}
    assert conn.sent[0][0] == "launch_draw"


def test_run_no_location():
    conn = make_conn()
    caller = MockCaller(location=None, conn=conn)
    with patch("atheriz.commands.loggedin.mapedit.get_map_handler", return_value=MockMapHandler()):
        DrawCommand().run(caller, None)
    assert conn.sent == []
    assert caller.messages == ["You must be in a valid location to open the map editor."]


# ==================== Inputfunc tests ====================


def test_map_edit_handshake():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    conn = make_conn()
    with patch("atheriz.inputfuncs.get_map_handler", return_value=MockMapHandler()):
        InputFuncs().map_edit(conn, [key, 0, []], {})
    assert len(conn.sent) == 1
    cmd, args, _ = conn.sent[0]
    assert cmd == "map_ack"
    assert args[0] == 0
    assert args[1] != key
    assert mapedit._chains[args[1]].key == args[1]


def test_map_edit_applies_color_cells():
    mi = make_mi({})
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    conn = make_conn()
    with patch("atheriz.inputfuncs.get_map_handler", return_value=mh):
        InputFuncs().map_edit(conn, [key, 0, []], {})
        handshake_key = conn.sent[0][1][1]
        InputFuncs().map_edit(
            conn,
            [
                handshake_key,
                1,
                [
                    [2, 3, "B", [255, 0, 0], [-1, -1, -1], ["bold"]],
                    [4, 4, "C", [10, 20, 30], [1, 2, 3], ["italic", "underline"]],
                ],
            ],
            {},
        )
    assert mi.pre_grid[(2, 3)] == "\x1b[1m\x1b[38;2;255;0;0m\x1b[48;2;0;0;0mB\x1b[0m"
    assert mi.pre_grid[(4, 4)] == "\x1b[4m\x1b[3m\x1b[38;2;10;20;30m\x1b[48;2;1;2;3mC\x1b[0m"
    assert len(conn.sent) == 2
    assert conn.sent[1][0] == "map_ack"
    assert conn.sent[1][1][0] == 1


def test_map_edit_applies_cells():
    mi = make_mi({(2, 3): "A"})
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    conn = make_conn()
    with patch("atheriz.inputfuncs.get_map_handler", return_value=mh):
        InputFuncs().map_edit(conn, [key, 0, []], {})
        handshake_key = conn.sent[0][1][1]
        InputFuncs().map_edit(conn, [handshake_key, 1, [[2, 3, "B"], [9, 9, ""], [4, 4, "C"]]], {})
    assert mi.pre_grid[(2, 3)] == "B"
    assert mi.pre_grid[(4, 4)] == "C"
    assert (9, 9) not in mi.pre_grid
    assert (2, 3) in mi.pre_grid
    assert len(conn.sent) == 2
    assert conn.sent[1][0] == "map_ack"
    assert conn.sent[1][1][0] == 1


def test_map_edit_retry_does_not_reapply():
    mi = make_mi({})
    mh = MockMapHandler()
    mh.set_mapinfo("TestArea", 0, mi)
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    conn = make_conn()
    with patch("atheriz.inputfuncs.get_map_handler", return_value=mh):
        InputFuncs().map_edit(conn, [key, 0, []], {})
        handshake_key = conn.sent[0][1][1]
        InputFuncs().map_edit(conn, [handshake_key, 1, [[0, 0, "X"]]], {})
        edited_key = conn.sent[1][1][1]
        InputFuncs().map_edit(conn, [handshake_key, 1, [[0, 0, "Y"]]], {})
    assert mi.pre_grid[(0, 0)] == "X"
    assert len(conn.sent) == 3
    assert conn.sent[2][0] == "map_ack"
    assert conn.sent[2][1][1] == edited_key


def test_map_edit_reject_unknown_key():
    conn = make_conn()
    with patch("atheriz.inputfuncs.get_map_handler", return_value=MockMapHandler()):
        InputFuncs().map_edit(conn, ["bogus", 1, []], {})
    assert len(conn.sent) == 1
    cmd, args, _ = conn.sent[0]
    assert cmd == "map_edit_reject"
    assert args == ["unknown_key"]


def test_map_edit_reject_replay():
    key = mapedit.grant("10.0.0.1", "TestArea", 0)
    conn = make_conn()
    with patch("atheriz.inputfuncs.get_map_handler", return_value=MockMapHandler()):
        InputFuncs().map_edit(conn, [key, 0, []], {})
        current = conn.sent[0][1][1]
        InputFuncs().map_edit(conn, [current, 0, []], {})
    assert conn.sent[1][0] == "map_edit_reject"
    assert conn.sent[1][1] == ["replay"]


def test_map_edit_malformed_args_are_ignored():
    conn = make_conn()
    for args in ([], ["key"], [123, 0, []], ["key", "0", []], ["key", 0, "cells"], ["key", 0, [[1]]], ["key", 0, [["a", "b", "c"]]], ["key", 0, [[0, 0, 1]]]):
        with patch("atheriz.inputfuncs.get_map_handler", return_value=MockMapHandler()):
            InputFuncs().map_edit(conn, args, {})
    assert conn.sent == []
