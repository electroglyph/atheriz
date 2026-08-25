"""
Extensive tests for wander tickable leak, nofollow dangling edge, deep delete coverage, and door cleanup.

Wander: grid with no random node returns None should not create Wanderer.
Nofollow: preserve builder followers, keep/destroy FollowScript correctly.
Delete: truncation at MAX_SEARCH_DEPTH keeps deep survivors detached without dangling, full delete when MAX increased, cycle safe.
Remove door: minimal sanity check that links and glyph are removed.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from atheriz.utils import Coord
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.globals.objects import _ALL_OBJECTS, get as objects_get
from atheriz.globals.get import get_node_handler, get_async_ticker
from atheriz import settings
from atheriz.commands.loggedin.wander import WanderCommand, Wanderer
from atheriz.commands.loggedin.follow import FollowCommand, NoFollowCommand, FollowScript


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wander_handler(area_name="WanderArea", z=0):
    nh = NodeHandler()
    area = NodeArea(name=area_name)
    grid = NodeGrid(area=area_name, z=z)
    n1 = Node(coord=Coord(area_name, 0, 0, z))
    n2 = Node(coord=Coord(area_name, 1, 0, z))
    n1.add_link(NodeLink("east", Coord(area_name, 1, 0, z)))
    n2.add_link(NodeLink("west", Coord(area_name, 0, 0, z)))
    grid.add_node(n1)
    grid.add_node(n2)
    area.add_grid(grid)
    nh.add_area(area)
    return nh, n1, n2, area, grid

def _setup_follow_nodes(area_name="FollowArea"):
    handler = NodeHandler()
    area = NodeArea(name=area_name)
    grid = NodeGrid(z=0)
    node1 = Node(coord=Coord(area_name, 0, 0, 0))
    link_n = NodeLink(name="north", coord=Coord(area_name, 0, 1, 0))
    node1.add_link(link_n)
    node2 = Node(coord=Coord(area_name, 0, 1, 0))
    link_s = NodeLink(name="south", coord=Coord(area_name, 0, 0, 0))
    node2.add_link(link_s)
    grid.add_node(node1)
    grid.add_node(node2)
    area.add_grid(grid)
    handler.add_area(area)
    return node1, node2

def _make_follow_pair(node, builder_follower=False, normal_follower=True):
    leader = Object.create(None, "Leader", is_pc=True)
    leader.is_connected = True
    leader.location = node
    node.add_object(leader)
    leader.msg = MagicMock()
    followers = []
    cmd = FollowCommand()
    if builder_follower:
        bf = Object.create(None, "BuilderFollower", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node
        node.add_object(bf)
        bf.msg = MagicMock()
        cmd.run(bf, MagicMock(target="Leader"))
        followers.append(bf)
    if normal_follower:
        nf = Object.create(None, "NormalFollower", is_pc=True)
        nf.is_connected = True
        nf.location = node
        node.add_object(nf)
        nf.msg = MagicMock()
        cmd.run(nf, MagicMock(target="Leader"))
        followers.append(nf)
    return leader, followers

class _MockMapInfo:
    def __init__(self):
        self.lock = MagicMock()
        self.lock.__enter__ = MagicMock(return_value=None)
        self.lock.__exit__ = MagicMock(return_value=False)
        self.post_grid = {}
        self.pre_grid = None
        self.map_changed = False
    def update_grid(self, coord, symbol):
        pass
    def render(self, force=False):
        pass
class _MockMapHandler:
    def get_mapinfo(self, area, z):
        return _MockMapInfo()


# ===========================================================================
# M7: wander tickable leak
# ===========================================================================

class TestWanderTickableLeak:

    def test_wander_no_random_node_creates_nothing_no_tickable_leak(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7A1")
        caller = Object.create(None, "Builder", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        before_ids = set(_ALL_OBJECTS.keys())
        ticker = get_async_ticker()
        before_slots = {k: set(v.coros) for k, v in ticker.slots.items()} if hasattr(ticker, "slots") else {}
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=None):
            WanderCommand().run(caller, MagicMock(count=3))
        after_ids = set(_ALL_OBJECTS.keys())
        new_ids = after_ids - before_ids
        wanderers = [objects_get(i)[0] for i in new_ids if objects_get(i) and objects_get(i)[0].name.startswith("Wanderer")]
        assert len(wanderers) == 0, f"no wanderer should be created when get_random_node returns None, got {new_ids}"
        assert not any("Wanderer" in str(objects_get(i)[0].name) for i in new_ids if objects_get(i))
        after_slots = {k: set(v.coros) for k, v in ticker.slots.items()} if hasattr(ticker, "slots") else {}
        # no new coros added
        for interval, coros in after_slots.items():
            before = before_slots.get(interval, set())
            assert coros == before or coros.issubset(before) or len(coros - before) == 0, "ticker leak when no random node"

    def test_wander_no_random_node_wanderer_create_not_called(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7A2")
        caller = Object.create(None, "Builder2", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=None), \
             patch.object(Wanderer, "create", wraps=Wanderer.create) as mock_create:
            WanderCommand().run(caller, MagicMock(count=5))
            mock_create.assert_not_called()

    def test_wander_no_random_node_add_coro_not_called(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7A3")
        caller = Object.create(None, "Builder3", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        ticker = get_async_ticker()
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=None), \
             patch.object(ticker, "add_coro", wraps=ticker.add_coro) as mock_add:
            WanderCommand().run(caller, MagicMock(count=4))
            # add_coro should not be called for wanderers (may be called for other intervals but filter)
            # We check that no call with wanderer at_tick
            wanderer_calls = [c for c in mock_add.call_args_list if "at_tick" in str(c)]
            # Alternatively count total calls before vs after filtered to wanderer create path
            # Since no wanderer created, no tickable add should happen for wanderers
            assert mock_add.call_count == 0 or all("Wanderer" not in str(call) for call in mock_add.call_args_list)

    def test_wander_success_creates_wanderer_correctly(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7B1")
        caller = Object.create(None, "Builder4", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        before = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=n2):
            WanderCommand().run(caller, MagicMock(count=1))
        after = set(_ALL_OBJECTS.keys())
        new_ids = after - before
        assert len(new_ids) == 1, f"expected 1 wanderer, got {len(new_ids)}"
        wanderer = objects_get(list(new_ids)[0])[0]
        assert wanderer.name.startswith("Wanderer")
        assert wanderer.is_tickable is True
        assert wanderer.is_npc is True
        assert wanderer.is_mapable is True
        assert wanderer.location is n2

    def test_wander_success_wanderer_is_tickable_and_in_ticker(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7B2")
        caller = Object.create(None, "Builder5", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        before = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=n2):
            WanderCommand().run(caller, MagicMock(count=1))
        after = set(_ALL_OBJECTS.keys())
        new_ids = after - before
        assert len(new_ids) == 1, f"expected 1 wanderer, got {new_ids}"
        wanderer = objects_get(list(new_ids)[0])[0]
        assert wanderer.is_tickable is True, "wanderer should be tickable"
        ticker = get_async_ticker()
        found = False
        details = []
        for interval, slot in ticker.slots.items():
            with slot.lock:
                for coro in list(slot.coros):
                    self_obj = getattr(coro, "__self__", None)
                    details.append((interval, getattr(self_obj, "id", None), type(self_obj).__name__ if self_obj else None, repr(coro)[:120]))
                    if self_obj is wanderer:
                        found = True
                    elif self_obj is not None and getattr(self_obj, "id", None) == wanderer.id:
                        found = True
                    elif isinstance(self_obj, Wanderer):
                        found = True
            if found:
                break
        assert found, f"Wanderer {wanderer.id} at_tick should be registered in ticker; slots={details} ticker_keys={list(ticker.slots.keys())}"

    def test_wander_multiple_success_creates_requested_count(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7B3")
        caller = Object.create(None, "Builder6", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        before = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=n2):
            WanderCommand().run(caller, MagicMock(count=5))
        after = set(_ALL_OBJECTS.keys())
        new_ids = after - before
        assert len(new_ids) == 5
        for nid in new_ids:
            obj = objects_get(nid)[0]
            assert obj.is_tickable is True
            assert obj.location is n2

    def test_wander_partial_none_only_valid_created(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7C1")
        caller = Object.create(None, "Builder7", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        n3 = Node(coord=Coord("M7C1", 2, 2, 0))
        grid.add_node(n3)
        before = set(_ALL_OBJECTS.keys())
        returns = [None, n2, None, n3, None]
        def side_effect():
            return returns.pop(0) if returns else None
        # need to patch to return sequence; use side_effect list
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", side_effect=[None, n2, None, n3, None]):
            WanderCommand().run(caller, MagicMock(count=5))
        after = set(_ALL_OBJECTS.keys())
        new_ids = after - before
        assert len(new_ids) == 2, f"only 2 valid nodes should create 2 wanderers, got {len(new_ids)}"
        locs = {objects_get(i)[0].location for i in new_ids}
        assert n2 in locs and n3 in locs

    def test_wander_ticker_count_matches_created_when_mixed(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7C2")
        caller = Object.create(None, "Builder8", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        ticker = get_async_ticker()
        before_ticker_count = sum(len(v.coros) for v in ticker.slots.values())
        before_objs = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", side_effect=[None, n2, n2, None, n2]):
            WanderCommand().run(caller, MagicMock(count=5))
        after_objs = set(_ALL_OBJECTS.keys())
        new_objs = after_objs - before_objs
        after_ticker_count = sum(len(v.coros) for v in ticker.slots.values())
        assert len(new_objs) == 3
        assert after_ticker_count - before_ticker_count == 3, "ticker should have exactly 3 new coros for 3 wanderers"

    def test_wander_zero_count_no_creation(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7D1")
        caller = Object.create(None, "Builder9", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        before = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(NodeGrid, "get_random_node", return_value=n2):
            WanderCommand().run(caller, MagicMock(count=0))
        after = set(_ALL_OBJECTS.keys())
        new_ids = after - before
        assert len(new_ids) == 10, f"count 0 is falsy and defaults to 10, got {len(new_ids)}"

    def test_wander_reorder_fix_source_order(self, global_test_env):
        import pathlib
        p = pathlib.Path("/home/anon/atheriz/atheriz/commands/loggedin/wander.py")
        src = p.read_text(encoding="utf-8")
        loop_start = src.find("for i in range(count):")
        assert loop_start != -1
        segment = src[loop_start:loop_start+2000]
        idx_rand = segment.find("get_random_node")
        idx_create = segment.find("Wanderer.create")
        assert idx_rand != -1 and idx_create != -1, "both get_random_node and Wanderer.create should be in loop"
        assert idx_rand < idx_create, "M7 fix requires get_random_node check BEFORE Wanderer.create to avoid tickable leak"

    def test_wander_no_leak_when_area_missing_returns_early(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7E1")
        caller = Object.create(None, "Builder10", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = n1
        caller.msg = MagicMock()
        # Make get_area return None
        mock_nh = MagicMock()
        mock_nh.get_area.return_value = None
        before = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=mock_nh):
            WanderCommand().run(caller, MagicMock(count=2))
        after = set(_ALL_OBJECTS.keys())
        assert after == before
        caller.msg.assert_called_with("Could not find your current area.")

    def test_wander_no_leak_when_not_in_node(self, global_test_env):
        nh, n1, n2, area, grid = _make_wander_handler("M7E2")
        caller = Object.create(None, "Builder11", is_pc=True)
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.location = Object.create(None, "NotANode")
        caller.msg = MagicMock()
        before = set(_ALL_OBJECTS.keys())
        with patch("atheriz.commands.loggedin.wander.get_node_handler", return_value=nh), \
             patch.object(Wanderer, "create") as mock_create:
            WanderCommand().run(caller, MagicMock(count=2))
            mock_create.assert_not_called()
        after = set(_ALL_OBJECTS.keys())
        # Only the NotANode container exists beyond before, no wanderers
        new_wanderers = [i for i in (after - before) if objects_get(i) and getattr(objects_get(i)[0], "name", "").startswith("Wanderer")]
        assert len(new_wanderers) == 0


# ===========================================================================
# M8: nofollow dangling edge
# ===========================================================================

class TestNofollowDanglingEdge:

    def test_nofollow_preserves_builder_follower_and_script(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A1")
        leader = Object.create(None, "LeaderA", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        leader.msg = MagicMock()
        bf = Object.create(None, "BuilderF", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node1
        node1.add_object(bf)
        bf.msg = MagicMock()
        nf = Object.create(None, "NormalF", is_pc=True)
        nf.is_connected = True
        nf.location = node1
        node1.add_object(nf)
        nf.msg = MagicMock()
        cmd = FollowCommand()
        cmd.run(bf, MagicMock(target="LeaderA"))
        cmd.run(nf, MagicMock(target="LeaderA"))
        assert bf.following == leader.id
        assert nf.following == leader.id
        assert bf.id in leader.followers
        assert nf.id in leader.followers
        assert len(leader.get_scripts_by_type("FollowScript")) == 1
        # now nofollow
        nofollow = NoFollowCommand()
        nofollow.run(leader, None)
        assert leader.no_follow is True
        assert bf.id in leader.followers, "builder should remain"
        assert nf.id not in leader.followers, "normal should be removed"
        assert bf.following == leader.id, "builder following should be preserved (no dangling)"
        assert nf.following is None, "normal following cleared"
        assert len(leader.get_scripts_by_type("FollowScript")) == 1, "script preserved when builder remains"
        assert bf.following is not None
        assert leader.followers == {bf.id}

    def test_nofollow_removes_script_when_only_normal_followers(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A2")
        leader = Object.create(None, "LeaderB", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        f1 = Object.create(None, "F1", is_pc=True)
        f1.is_connected = True
        f1.location = node1
        node1.add_object(f1)
        f1.msg = MagicMock()
        FollowCommand().run(f1, MagicMock(target="LeaderB"))
        assert len(leader.get_scripts_by_type("FollowScript")) == 1
        NoFollowCommand().run(leader, None)
        assert leader.no_follow is True
        assert len(leader.followers) == 0
        assert f1.following is None
        assert len(leader.get_scripts_by_type("FollowScript")) == 0, "script should be deleted when no followers remain"

    def test_nofollow_only_builder_keeps_everything(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A3")
        leader = Object.create(None, "LeaderC", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        bf = Object.create(None, "BuilderC", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node1
        node1.add_object(bf)
        FollowCommand().run(bf, MagicMock(target="LeaderC"))
        assert bf.following == leader.id
        assert bf.id in leader.followers
        assert len(leader.get_scripts_by_type("FollowScript")) == 1
        NoFollowCommand().run(leader, None)
        assert leader.no_follow is True
        assert bf.id in leader.followers
        assert bf.following == leader.id
        assert len(leader.get_scripts_by_type("FollowScript")) == 1

    def test_nofollow_multiple_mixed_preserves_all_builders(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A4")
        leader = Object.create(None, "LeaderD", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        builders = []
        normals = []
        for i in range(3):
            b = Object.create(None, f"Builder{i}", is_pc=True)
            b.privilege_level = settings.Privilege.Builder
            b.quelled = False
            b.is_connected = True
            b.location = node1
            node1.add_object(b)
            FollowCommand().run(b, MagicMock(target="LeaderD"))
            builders.append(b)
        for i in range(2):
            n = Object.create(None, f"Normal{i}", is_pc=True)
            n.is_connected = True
            n.location = node1
            node1.add_object(n)
            FollowCommand().run(n, MagicMock(target="LeaderD"))
            normals.append(n)
        assert len(leader.followers) == 5
        NoFollowCommand().run(leader, None)
        assert len(leader.followers) == 3
        for b in builders:
            assert b.id in leader.followers
            assert b.following == leader.id
        for n in normals:
            assert n.id not in leader.followers
            assert n.following is None
        assert len(leader.get_scripts_by_type("FollowScript")) == 1

    def test_nofollow_clears_following_dict_not_leaving_dangling(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A5")
        leader = Object.create(None, "LeaderE", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        bf = Object.create(None, "BuilderE", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node1
        node1.add_object(bf)
        nf = Object.create(None, "NormalE", is_pc=True)
        nf.is_connected = True
        nf.location = node1
        node1.add_object(nf)
        FollowCommand().run(bf, MagicMock(target="LeaderE"))
        FollowCommand().run(nf, MagicMock(target="LeaderE"))
        NoFollowCommand().run(leader, None)
        # dangling check: builder's following still valid and leader still has it
        assert bf.following == leader.id
        assert bf.id in leader.followers
        # normal's following cleared, leader does not have it
        assert nf.following is None
        assert nf.id not in leader.followers
        # ensure no other dangling: every follower whose following==leader must be in leader.followers
        for fid in list(leader.followers):
            f = objects_get(fid)[0]
            assert f.following == leader.id
        # every follower that was removed must have following None
        assert nf.following is None

    def test_nofollow_toggle_off_preserves_builder_still_following(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A6")
        leader = Object.create(None, "LeaderF", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        bf = Object.create(None, "BuilderF2", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node1
        node1.add_object(bf)
        nf = Object.create(None, "NormalF2", is_pc=True)
        nf.is_connected = True
        nf.location = node1
        node1.add_object(nf)
        FollowCommand().run(bf, MagicMock(target="LeaderF"))
        FollowCommand().run(nf, MagicMock(target="LeaderF"))
        NoFollowCommand().run(leader, None)
        assert leader.no_follow is True
        NoFollowCommand().run(leader, None)
        assert leader.no_follow is False
        # builder still following, normal not
        assert bf.following == leader.id
        assert bf.id in leader.followers
        assert nf.following is None
        assert nf.id not in leader.followers
        # script still exists because builder remains
        assert len(leader.get_scripts_by_type("FollowScript")) == 1
        # normal can now follow again if allowed
        nf.msg = MagicMock()
        FollowCommand().run(nf, MagicMock(target="LeaderF"))
        assert nf.following == leader.id
        assert nf.id in leader.followers

    def test_nofollow_following_dict_cleanup_builder_vs_normal(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A7")
        leader = Object.create(None, "LeaderG", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        # create 1 builder, 2 normals
        bf = Object.create(None, "BuilderG", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node1
        node1.add_object(bf)
        n1 = Object.create(None, "NormalG1", is_pc=True)
        n1.is_connected = True
        n1.location = node1
        node1.add_object(n1)
        n2 = Object.create(None, "NormalG2", is_pc=True)
        n2.is_connected = True
        n2.location = node1
        node1.add_object(n2)
        for f in [bf, n1, n2]:
            FollowCommand().run(f, MagicMock(target="LeaderG"))
        assert len(leader.followers) == 3
        NoFollowCommand().run(leader, None)
        # after, only builder remains
        assert leader.followers == {bf.id}
        assert bf.following == leader.id
        assert n1.following is None
        assert n2.following is None
        # second nofollow toggle off should not clear builder
        NoFollowCommand().run(leader, None)
        assert leader.followers == {bf.id}

    def test_nofollow_no_followers_no_script_deletion_crash(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A8")
        leader = Object.create(None, "LeaderH", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        # no followers yet
        assert len(leader.get_scripts_by_type("FollowScript")) == 0
        NoFollowCommand().run(leader, None)
        assert leader.no_follow is True
        assert len(leader.followers) == 0
        assert len(leader.get_scripts_by_type("FollowScript")) == 0
        NoFollowCommand().run(leader, None)
        assert leader.no_follow is False

    def test_nofollow_script_preserved_if_builder_remains_even_after_normal_cleared(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A9")
        leader = Object.create(None, "LeaderI", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        bf = Object.create(None, "BuilderI", is_pc=True)
        bf.privilege_level = settings.Privilege.Builder
        bf.quelled = False
        bf.is_connected = True
        bf.location = node1
        node1.add_object(bf)
        nf = Object.create(None, "NormalI", is_pc=True)
        nf.is_connected = True
        nf.location = node1
        node1.add_object(nf)
        FollowCommand().run(bf, MagicMock(target="LeaderI"))
        FollowCommand().run(nf, MagicMock(target="LeaderI"))
        scripts_before = leader.get_scripts_by_type("FollowScript")
        assert len(scripts_before) == 1
        sid_before = scripts_before[0].id
        NoFollowCommand().run(leader, None)
        scripts_after = leader.get_scripts_by_type("FollowScript")
        assert len(scripts_after) == 1
        assert scripts_after[0].id == sid_before

    def test_nofollow_script_deleted_when_all_normal_and_no_builder(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A10")
        leader = Object.create(None, "LeaderJ", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        normals = []
        for i in range(3):
            n = Object.create(None, f"Nj{i}", is_pc=True)
            n.is_connected = True
            n.location = node1
            node1.add_object(n)
            FollowCommand().run(n, MagicMock(target="LeaderJ"))
            normals.append(n)
        assert len(leader.followers) == 3
        assert len(leader.get_scripts_by_type("FollowScript")) == 1
        NoFollowCommand().run(leader, None)
        assert len(leader.followers) == 0
        for n in normals:
            assert n.following is None
        assert len(leader.get_scripts_by_type("FollowScript")) == 0

    def test_nofollow_quelled_builder_treated_as_non_builder(self, global_test_env):
        node1, _ = _setup_follow_nodes("M8A11")
        leader = Object.create(None, "LeaderK", is_pc=True)
        leader.is_connected = True
        leader.location = node1
        node1.add_object(leader)
        qb = Object.create(None, "QuelledBuilder", is_pc=True)
        qb.privilege_level = settings.Privilege.Builder
        qb.quelled = True
        qb.is_connected = True
        qb.location = node1
        node1.add_object(qb)
        assert qb.is_builder is False, "quelled builder should not be considered builder"
        FollowCommand().run(qb, MagicMock(target="LeaderK"))
        assert qb.following == leader.id
        assert qb.id in leader.followers
        NoFollowCommand().run(leader, None)
        assert qb.id not in leader.followers
        assert qb.following is None
        assert len(leader.get_scripts_by_type("FollowScript")) == 0


# ===========================================================================
# M11: _delete_recursive depth skip
# ===========================================================================

class TestDeleteRecursiveDepthSkip:

    def _make_admin(self):
        admin = Object.create(None, "AdminM11")
        admin.privilege_level = settings.Privilege.Admin
        return admin

    def test_deep_chain_120_all_deleted(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 500)
        admin = self._make_admin()
        outer = Object.create(None, "outer120", is_container=True)
        chain = [outer]
        prev = outer
        for i in range(120):
            c = Object.create(None, f"chain120_{i}", is_container=True)
            c.move_to(prev)
            chain.append(c)
            prev = c
        leaf = Object.create(None, "leaf120", is_item=True)
        leaf.move_to(prev)
        all_ids = [o.id for o in chain] + [leaf.id]
        for oid in all_ids:
            assert objects_get(oid), f"pre-delete {oid} missing"
        outer.delete(admin, recursive=True)
        for oid in all_ids:
            assert not objects_get(oid), f"oid {oid} should be deleted (deep >100)"
            assert oid not in _ALL_OBJECTS
        assert outer.is_deleted is True
        assert leaf.is_deleted is True
        assert leaf.location is None

    def test_deep_chain_200_all_deleted(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 500)
        admin = self._make_admin()
        outer = Object.create(None, "outer200", is_container=True)
        chain = [outer]
        prev = outer
        for i in range(200):
            c = Object.create(None, f"chain200_{i}", is_container=True)
            c.move_to(prev)
            chain.append(c)
            prev = c
        all_ids = [o.id for o in chain]
        outer.delete(admin, recursive=True)
        for oid in all_ids:
            assert not objects_get(oid)
            assert oid not in _ALL_OBJECTS
        leaked = [oid for oid in all_ids if oid in _ALL_OBJECTS]
        assert leaked == []

    def test_deep_chain_exact_boundary(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 500)
        admin = self._make_admin()
        for depth in [100, 101, 102]:
            outer = Object.create(None, f"outerB{depth}", is_container=True)
            chain = [outer]
            prev = outer
            for i in range(depth):
                c = Object.create(None, f"b{depth}_{i}", is_container=True)
                c.move_to(prev)
                chain.append(c)
                prev = c
            all_ids = [o.id for o in chain]
            outer.delete(admin, recursive=True)
            for oid in all_ids:
                assert not objects_get(oid), f"depth {depth} oid {oid} should be deleted even beyond old MAX_SEARCH_DEPTH"
            assert outer.is_deleted

    def test_deep_chain_truncation_survivors_detached_not_leaked(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 5)
        admin = self._make_admin()
        outer = Object.create(None, "outerTrunc", is_container=True)
        chain = [outer]
        prev = outer
        for i in range(10):
            c = Object.create(None, f"trunc_{i}", is_container=True)
            c.move_to(prev)
            chain.append(c)
            prev = c
        deepest = chain[-1]
        outer.delete(admin, recursive=True)
        assert not objects_get(outer.id)
        assert objects_get(deepest.id), "deep objects beyond limit should survive truncation"
        survivor = objects_get(chain[5].id)[0]
        assert survivor.location is None, "truncated survivor should be detached, not dangling to deleted parent"
        assert survivor.id not in _ALL_OBJECTS or objects_get(survivor.id)
        for i in range(4):
            assert not objects_get(chain[i+1].id), f"trunc_{i} depth {i+1}<5 should be deleted"
        for i in range(5, 10):
            assert objects_get(chain[i+1].id), f"trunc_{i} depth {i+1}>=5 should survive"

    def test_deep_chain_branching_all_deleted(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 500)
        admin = self._make_admin()
        outer = Object.create(None, "outerBranch", is_container=True)
        branches = []
        for b in range(3):
            prev = outer
            for i in range(50):
                c = Object.create(None, f"branch{b}_{i}", is_container=True)
                if i == 0:
                    c.move_to(outer)
                    branches.append(c)
                    prev = c
                else:
                    c.move_to(prev)
                    prev = c
        tail_prev = branches[0]
        deepest = tail_prev
        while deepest.contents:
            nxt = deepest.contents[0]
            deepest = nxt
        for i in range(60):
            c = Object.create(None, f"tail_{i}", is_container=True)
            c.move_to(deepest)
            deepest = c
        all_ids_before = set(_ALL_OBJECTS.keys())
        outer.delete(admin, recursive=True)
        for oid in list(all_ids_before):
            obj = objects_get(oid)
            if obj:
                assert obj[0].id != outer.id
                if obj[0].name == "AdminM11":
                    continue
                pass
        assert outer.is_deleted
        remaining_names = [o.name for o in _ALL_OBJECTS.values()]
        assert not any(n.startswith("branch") or n.startswith("tail_") for n in remaining_names), f"leaked branch objects: {remaining_names}"

    def test_cycle_two_nodes_no_infinite_loop(self, global_test_env):
        admin = self._make_admin()
        a = Object.create(None, "CycleA", is_container=True)
        b = Object.create(None, "CycleB", is_container=True)
        b.move_to(a)
        # manually create cycle: a inside b as well via direct _contents bypassing move_to guard
        with b.lock:
            b._contents.add(a.id)
        # also set locations to simulate cycle? Location not needed for contents traversal, but set to create loop
        # Create seen cycle via _contents only is enough; delete should handle seen
        all_ids = [a.id, b.id]
        # Should not hang
        a.delete(admin, recursive=True)
        for oid in all_ids:
            assert not objects_get(oid), f"cycle oid {oid} should be deleted"
            assert oid not in _ALL_OBJECTS

    def test_cycle_three_nodes(self, global_test_env):
        admin = self._make_admin()
        x = Object.create(None, "CX", is_container=True)
        y = Object.create(None, "CY", is_container=True)
        z = Object.create(None, "CZ", is_container=True)
        y.move_to(x)
        z.move_to(y)
        # create cycle z -> x
        with z.lock:
            z._contents.add(x.id)
        x.delete(admin, recursive=True)
        for oid in [x.id, y.id, z.id]:
            assert not objects_get(oid)
            assert oid not in _ALL_OBJECTS

    def test_cycle_self_containment(self, global_test_env):
        admin = self._make_admin()
        o = Object.create(None, "SelfContain", is_container=True)
        # self loop
        with o.lock:
            o._contents.add(o.id)
        o.delete(admin, recursive=True)
        assert not objects_get(o.id)
        assert o.id not in _ALL_OBJECTS
        assert o.is_deleted is True

    def test_location_cleared_after_deep_delete(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 500)
        admin = self._make_admin()
        outer = Object.create(None, "outerLoc", is_container=True)
        mid = Object.create(None, "midLoc", is_container=True)
        mid.move_to(outer)
        leaf = Object.create(None, "leafLoc", is_item=True)
        leaf.move_to(mid)
        prev = leaf
        for i in range(110):
            c = Object.create(None, f"deepLeaf{i}", is_container=True)
            c.move_to(prev)
            prev = c
        deepest = prev
        deepest_id = deepest.id
        outer.delete(admin, recursive=True)
        for obj in [outer, mid, leaf, deepest]:
            assert obj.is_deleted is True
            assert obj.location is None
            assert obj.id not in _ALL_OBJECTS
        assert not objects_get(deepest_id)

    def test_is_deleted_flag_and_globals_removal(self, global_test_env):
        admin = self._make_admin()
        outer = Object.create(None, "outerFlag", is_container=True)
        inner = Object.create(None, "innerFlag", is_container=True)
        inner.move_to(outer)
        outer.delete(admin, recursive=True)
        assert outer.is_deleted is True
        assert inner.is_deleted is True
        assert outer.id not in _ALL_OBJECTS
        assert inner.id not in _ALL_OBJECTS

    def test_delete_preserves_unrelated_objects(self, global_test_env):
        admin = self._make_admin()
        outer = Object.create(None, "outerPreserve", is_container=True)
        inner = Object.create(None, "innerPreserve", is_container=True)
        inner.move_to(outer)
        unrelated = Object.create(None, "unrelated", is_container=True)
        outer.delete(admin, recursive=True)
        assert not objects_get(outer.id)
        assert not objects_get(inner.id)
        assert objects_get(unrelated.id), "unrelated should survive"
        assert unrelated.id in _ALL_OBJECTS

    def test_max_search_depth_setting_still_100(self, global_test_env):
        assert settings.MAX_SEARCH_DEPTH == 100

    def test_delete_recursive_uses_iterative_not_recursionerror(self, global_test_env):
        admin = self._make_admin()
        outer = Object.create(None, "outerIter", is_container=True)
        prev = outer
        for i in range(150):
            c = Object.create(None, f"iter{i}", is_container=True)
            c.move_to(prev)
            prev = c
        # This should not raise RecursionError even at 150 depth
        try:
            outer.delete(admin, recursive=True)
        except RecursionError:
            pytest.fail("delete should use iterative stack, not recurse")
        assert outer.is_deleted

    def test_old_guard_truncation_survivors_are_detached_not_dangling(self, global_test_env, monkeypatch):
        monkeypatch.setattr(settings, "MAX_SEARCH_DEPTH", 5)
        admin = self._make_admin()
        outer = Object.create(None, "outerLeakCheck", is_container=True)
        chain = [outer]
        prev = outer
        for i in range(10):
            c = Object.create(None, f"leak{i}", is_container=True)
            c.move_to(prev)
            chain.append(c)
            prev = c
        outer.delete(admin, recursive=True)
        for i in range(4):
            assert not objects_get(chain[i+1].id), f"leak{i} depth {i+1}<5 should be deleted"
        for i in range(5, 10):
            assert objects_get(chain[i+1].id), f"leak{i} depth {i+1}>=5 should survive truncation"
        first_survivor = objects_get(chain[6].id)[0] if False else objects_get(chain[5].id)[0]
        assert first_survivor.location is None, "first survivor beyond depth should be detached, not dangling to deleted parent"
        assert chain[5].id in _ALL_OBJECTS
        deeper = objects_get(chain[6].id)[0]
        assert deeper.location is first_survivor, "deeper survivor should remain under first survivor, not dangling"


# ===========================================================================
# M10: remove_door check (already covered elsewhere) — sanity
# ===========================================================================

class TestRemoveDoorCheck:

    def test_remove_door_cleans_links_and_doors_dict(self, global_test_env):
        nh = NodeHandler()
        mh = _MockMapHandler()
        area = NodeArea(name="M10Area")
        grid = NodeGrid(area="M10Area", z=0)
        n1 = Node(coord=Coord("M10Area", 0, 0, 0))
        n2 = Node(coord=Coord("M10Area", 0, 2, 0))
        n1.add_link(NodeLink("north", Coord("M10Area", 0, 2, 0), ["n"]))
        n2.add_link(NodeLink("south", Coord("M10Area", 0, 0, 0), ["s"]))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)
        from atheriz.objects.base_door import Door
        door = Door.create(
            from_coord=Coord("M10Area", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("M10Area", 0, 2, 0),
            to_exit="south",
            symbol_coord=(0, 1),
            closed_symbol=settings.NS_CLOSED_DOOR,
            open_symbol=settings.NS_OPEN_DOOR1,
            closed=True,
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)
        assert n1.get_link_by_name("north") is not None
        assert n2.get_link_by_name("south") is not None
        assert nh.get_doors(n1.coord) is not None
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)
        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
        assert n1.get_display_exits() == "" or "north" not in n1.get_display_exits()
        d1 = nh.get_doors(n1.coord)
        d2 = nh.get_doors(n2.coord)
        if d1:
            assert "north" not in d1
        if d2:
            assert "south" not in d2

    def test_remove_door_twice_idempotent(self, global_test_env):
        nh = NodeHandler()
        mh = _MockMapHandler()
        area = NodeArea(name="M10Area2")
        grid = NodeGrid(area="M10Area2", z=0)
        n1 = Node(coord=Coord("M10Area2", 0, 0, 0))
        n2 = Node(coord=Coord("M10Area2", 0, 2, 0))
        n1.add_link(NodeLink("north", Coord("M10Area2", 0, 2, 0)))
        n2.add_link(NodeLink("south", Coord("M10Area2", 0, 0, 0)))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)
        from atheriz.objects.base_door import Door
        door = Door.create(
            from_coord=Coord("M10Area2", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("M10Area2", 0, 2, 0),
            to_exit="south",
            symbol_coord=(0, 1),
            closed_symbol="X",
            open_symbol="O",
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)
            nh.remove_door(door)
            nh.remove_door(door)
        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
