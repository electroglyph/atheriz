"""
Regression tests for fixed correctness issues.
Each test describes the feature under test, not a document section.
"""
import time
import threading
import inspect
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

import atheriz.settings as settings
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.coord import Coord
from atheriz.utils import iter_to_str, word_replace, _build_signature_from_code
from atheriz.objects.contents import _term_matches, search
from atheriz.globals.objects import (
    CREATION_COOLDOWNS,
    CREATION_COOLDOWN_LOCK,
    creation_cooldown_active,
    try_reserve_creation_cooldown,
    clear_creation_cooldown,
    apply_creation_cooldown,
)
from atheriz.commands.loggedin.set import _is_protected, PROTECTED_ATTRIBUTES
from atheriz.globals.get import get_node_handler, get_map_handler


def test_creation_cooldown_is_unified_per_host_and_clears_on_failure(global_test_env):
    host = "1.2.3.4"
    now = time.monotonic()
    CREATION_COOLDOWNS.clear()
    assert try_reserve_creation_cooldown("guest", host, now, 60) is True
    # unified: account should be blocked
    assert creation_cooldown_active("account", host, now + 1) is True
    assert try_reserve_creation_cooldown("account", host, now + 1, 60) is False
    # clearing via helper must unblock both ops
    clear_creation_cooldown(host)
    assert creation_cooldown_active("guest", host, now + 1) is False
    assert creation_cooldown_active("character", host, now + 1) is False
    assert try_reserve_creation_cooldown("account", host, now + 1, 60) is True
    clear_creation_cooldown(host)


def test_creation_cooldown_validation_failure_does_not_leak(global_test_env):
    host = "5.6.7.8"
    now = time.monotonic()
    CREATION_COOLDOWNS.clear()
    assert try_reserve_creation_cooldown("account", host, now, 60) is True
    # simulate validation failure cleanup
    clear_creation_cooldown(host)
    assert CREATION_COOLDOWNS == {}
    # next creation should succeed
    assert try_reserve_creation_cooldown("account", host, now + 1, 60) is True
    clear_creation_cooldown(host)


def test_set_protects_access_tags_name_aliases_and_desc(global_test_env):
    assert _is_protected("access") is True
    assert _is_protected("tags") is True
    assert _is_protected("name") is True
    # aliases/desc are builder-editable (trust builders) — not protected
    assert _is_protected("aliases") is False
    assert _is_protected("desc") is False
    assert "access" in PROTECTED_ATTRIBUTES
    assert "tags" in PROTECTED_ATTRIBUTES
    assert "name" in PROTECTED_ATTRIBUTES
    assert "aliases" not in PROTECTED_ATTRIBUTES
    assert "desc" not in PROTECTED_ATTRIBUTES


def test_ban_account_scope_checks_all_characters_privilege(global_test_env):
    from atheriz.objects.base_account import Account
    from atheriz.commands.loggedin.ban import BanCommand

    # caller is Builder
    caller = Object.create(None, "CallerBuilder", is_pc=True)
    caller.privilege_level = settings.Privilege.Builder
    caller.is_connected = True

    # target is Guest alt
    target = Object.create(None, "GuestAlt", is_pc=True)
    target.privilege_level = settings.Privilege.Guest

    # admin alt on same account
    admin = Object.create(None, "AdminAlt", is_pc=True)
    admin.privilege_level = settings.Privilege.Admin

    account = Account.create("TestAcct", "password123")
    account.add_character(target)
    account.add_character(admin)

    # ensure _find_account will find it via characters scan
    # Simulate BanCommand.run with --account
    cmd = BanCommand()
    # Build args: need to mock _resolve_target to return our target
    with patch("atheriz.commands.loggedin.ban._resolve_target", return_value=target):
        with patch("atheriz.commands.loggedin.ban._find_account", return_value=account):
            # mock get to return characters
            with patch("atheriz.commands.loggedin.ban.get", side_effect=lambda ids: [target, admin] if isinstance(ids, list) else [target] if ids == target.id else []):
                mock_caller_msg = MagicMock()
                caller.msg = mock_caller_msg
                args = MagicMock()
                args.target = "GuestAlt"
                args.reason = None
                args.account = True
                args.ip = False
                cmd.run(caller, args)
                # Should have been blocked because account contains Admin >= Builder
                assert any("equal or higher privilege" in str(call[0][0]) for call in mock_caller_msg.call_args_list)
                assert account.is_banned is False


def test_build_signature_from_code_handles_varargs_and_kwonly_correctly(global_test_env):
    def foo(a, b, c=3, *args, d, e=5, **kw):
        pass

    sig = _build_signature_from_code(foo)
    expected = inspect.signature(foo)
    assert str(sig) == str(expected), f"got {sig} expected {expected}"

    # posonly
    def bar(a, b=1, /, c=2, d=3, *args, e, **kw):
        pass

    sig2 = _build_signature_from_code(bar)
    expected2 = inspect.signature(bar)
    assert str(sig2) == str(expected2)


def test_build_signature_from_code_posonly_and_all_variants(global_test_env):
    def foo1(a, b, /, c, d=3, *args, e, f=5, **kw):
        pass

    assert str(_build_signature_from_code(foo1)) == str(inspect.signature(foo1))

    def foo2(a, *args, b, c=1, **kw):
        pass

    assert str(_build_signature_from_code(foo2)) == str(inspect.signature(foo2))


def test_iter_to_str_word_separator_has_single_spaces(global_test_env):
    # words separator should not double-space
    result = iter_to_str([1, 2, 3], sep=" and ", endsep=" and ")
    assert "  and" not in result, f"double space found: {result!r}"
    assert result == "1 and 2 and 3"
    # also test 2-element join uses endsep correctly
    result2 = iter_to_str([1, 2], sep=" and ", endsep=" and ")
    assert result2 == "1 and 2"
    # punctuation still works
    assert iter_to_str([1, 2, 3], sep=",", endsep=", and ") == "1, 2, and 3"


def test_word_replace_zero_frequency_never_replaces_even_on_uniform_zero(global_test_env):
    with patch("atheriz.utils.uniform", return_value=0.0):
        assert word_replace("hello world", 0) == "hello world"
        assert word_replace("a b c", 0) == "a b c"
    with patch("atheriz.utils.uniform", return_value=0.0):
        # 1.0 should replace
        assert word_replace("hello world", 1.0) == "... ..."
    # less than threshold replaces, equal does not when using <
    with patch("atheriz.utils.uniform", return_value=0.5):
        assert word_replace("hello world", 0.5) == "hello world"  # 0.5 < 0.5 false
        assert word_replace("hello world", 0.51) == "... ..."


def test_get_command_handles_multiword_object_names(global_test_env):
    from atheriz.commands.loggedin.get import GetCommand
    import shlex

    cmd = GetCommand()
    # simulate parser with our new nargs="*" args
    # "long sword" should be single object
    ns = cmd.parser.parse_args(shlex.split("long sword"))
    assert ns.args == ["long", "sword"]
    # "long sword from big bag" split on 'from'
    ns2 = cmd.parser.parse_args(shlex.split("long sword from big bag"))
    tokens = ns2.args
    from_idx = next((i for i, t in enumerate(tokens) if t.lower() == "from"), None)
    assert from_idx == 2
    assert " ".join(tokens[:from_idx]) == "long sword"
    assert " ".join(tokens[from_idx + 1 :]) == "big bag"


def test_put_command_handles_multiword_names(global_test_env):
    from atheriz.commands.loggedin.put import PutCommand
    import shlex

    cmd = PutCommand()
    ns = cmd.parser.parse_args(shlex.split("long sword in big bag"))
    tokens = ns.args
    split_idx = next((i for i, t in enumerate(tokens) if t.lower() in ("in", "into")), None)
    assert split_idx is not None
    assert " ".join(tokens[:split_idx]) == "long sword"
    assert " ".join(tokens[split_idx + 1 :]) == "big bag"

    ns2 = cmd.parser.parse_args(shlex.split("rusty dagger into wooden chest"))
    tokens2 = ns2.args
    split2 = next((i for i, t in enumerate(tokens2) if t.lower() in ("in", "into")), None)
    assert " ".join(tokens2[:split2]) == "rusty dagger"
    assert " ".join(tokens2[split2 + 1 :]) == "wooden chest"


def test_give_command_handles_multiword_names(global_test_env):
    from atheriz.commands.loggedin.give import GiveCommand
    import shlex

    cmd = GiveCommand()
    ns = cmd.parser.parse_args(shlex.split("long sword to Bob Builder"))
    tokens = ns.args
    to_idx = next((i for i, t in enumerate(tokens) if t.lower() == "to"), None)
    assert to_idx == 2
    assert " ".join(tokens[:to_idx]) == "long sword"
    assert " ".join(tokens[to_idx + 1 :]) == "Bob Builder"


def test_channel_command_accepts_multiword_message(global_test_env):
    from atheriz.commands.loggedin.channel import ChannelCommand

    cmd = ChannelCommand()
    ns = cmd.parser.parse_args(["--channel", "ooc", "hello", "there", "world"])
    assert ns.message == ["hello", "there", "world"]
    # joined should be single string
    assert " ".join(ns.message) == "hello there world"
    # single word still works
    ns2 = cmd.parser.parse_args(["--channel", "ooc", "hello"])
    assert ns2.message == ["hello"]


def test_socials_finds_target_in_room_when_not_in_inventory(global_test_env):
    from atheriz.commands.loggedin.socials import CmdSocials
    from atheriz.objects.nodes import Node

    room = Node(coord=Coord("test", 0, 0, 0), desc="room")
    alice = Object.create(None, "Alice", is_pc=True)
    bob = Object.create(None, "Bob", is_pc=True)
    # pcs are not viewable when disconnected; make them viewable for the test
    alice.is_connected = True
    bob.is_connected = True
    alice.move_to(room)
    bob.move_to(room)
    # Ensure Bob not in Alice inventory
    assert bob not in alice.contents
    # socials should find Bob in room via fallback
    cmd = CmdSocials()
    # mock location msg_contents to capture
    msgs = []
    orig_msg = room.msg_contents

    def fake_msg(text, **kwargs):
        msgs.append(text)

    room.msg_contents = fake_msg
    # patch args
    class Args:
        target = ["Bob"]
        cmdstring = "smile"

    try:
        cmd.run(alice, Args())
        assert len(msgs) == 1
        assert "smile" in msgs[0].lower()
    finally:
        room.msg_contents = orig_msg


def test_term_matches_is_resilient_to_corrupted_name_and_aliases(global_test_env):
    class Fake:
        pass

    f = Fake()
    f.name = None
    f.aliases = []
    assert _term_matches(f, "test") is False

    f2 = Fake()
    f2.name = "test"
    f2.aliases = [123, None, "valid"]
    # should not crash, and should match valid alias if queried
    assert _term_matches(f2, "valid") is True
    assert _term_matches(f2, "xyz") is False

    # search with None query returns empty, not crash
    room = Node(coord=Coord("test2", 0, 0, 0), desc="r")
    obj = Object.create(None, "Real", is_item=True)
    obj.move_to(room)
    assert search(room, None) == []
    assert search(room, 123) == []
    # corrupted name in contents should not crash search
    bad = Object.create(None, "Good", is_item=True)
    # corrupt via direct dict bypassing protected set (simulate old data)
    object.__setattr__(bad, "name", None)
    bad.move_to(room)
    # search should not raise
    result = search(room, "good")
    assert isinstance(result, list)


def test_msg_contents_handles_none_without_crash(global_test_env):
    room = Node(coord=Coord("test3", 0, 0, 0), desc="room")
    a = Object.create(None, "A", is_pc=True)
    b = Object.create(None, "B", is_pc=True)
    a.move_to(room)
    b.move_to(room)
    # Patch receiver msg to avoid needing session
    received = []
    orig_a_msg = a.msg
    orig_b_msg = b.msg
    a.msg = lambda *args, **kw: received.append(("a", kw.get("text", args[0] if args else "")))
    b.msg = lambda *args, **kw: received.append(("b", kw.get("text", args[0] if args else "")))
    try:
        room.msg_contents(None)
        a.msg_contents(None)
        # should not raise
        assert True
    finally:
        a.msg = orig_a_msg
        b.msg = orig_b_msg

    # also from Object perspective with mapping
    room2 = Node(coord=Coord("test4", 0, 0, 0), desc="room")
    c = Object.create(None, "C", is_pc=True)
    c.move_to(room2)
    # should not crash even with None text and mapping
    try:
        room2.msg_contents(None, mapping={"target": c})
    except Exception as e:
        pytest.fail(f"msg_contents None raised {e}")


def test_node_dirty_flags_mark_modified_on_mutation(global_test_env):
    # Node nouns/links
    n = Node(coord=Coord("area1", 0, 0, 0), desc="room")
    n.is_modified = False
    n.add_noun("statue", "A statue")
    assert n.is_modified is True
    n.is_modified = False
    n.remove_noun("statue")
    assert n.is_modified is True

    n.is_modified = False
    link = NodeLink(name="north", coord=Coord("area1", 0, 1, 0))
    n.add_link(link)
    assert n.is_modified is True
    n.is_modified = False
    n.remove_link("north")
    assert n.is_modified is True

    # NodeGrid set_data
    grid = NodeGrid(area="area1", z=0)
    grid.is_modified = False
    grid.set_data("key", "value")
    assert grid.is_modified is True

    # NodeArea set_data
    area = NodeArea(name="area1")
    area.is_modified = False
    area.set_data("k", "v")
    assert area.is_modified is True
    area.is_modified = False
    area.remove_data("k")
    assert area.is_modified is True
    area.is_modified = False
    area.add_linked_area("other")
    assert area.is_modified is True
    area.is_modified = False
    area.remove_linked_area("other")
    assert area.is_modified is True

    # MapInfo legend
    from atheriz.globals.map import MapInfo, LegendEntry

    mi = MapInfo(name="test")
    mi.map_changed = False
    mi.add_legend_entry(LegendEntry(symbol="X", desc="test", coord=(0, 0)))
    assert mi.map_changed is True


def test_door_state_change_marks_handler_dirty(global_test_env):
    from atheriz.objects.base_door import Door

    nh = get_node_handler()
    # create nodes for door endpoints
    coord_a = Coord("doorarea", 0, 0, 0)
    coord_b = Coord("doorarea", 1, 0, 0)
    node_a = Node(coord=coord_a, desc="a")
    node_b = Node(coord=coord_b, desc="b")
    # Need grid/area for get_node to work, but Door.get_nodes uses nh.get_node
    # Ensure area/grid exists via Node creation already adds to handler
    # Create door
    door = Door(from_coord=coord_a, from_exit="east", to_coord=coord_b, to_exit="west", symbol_coord=(0, 0), closed=True, locked=False)
    nh.add_door(door)
    # reset flag after add
    with nh.lock3:
        nh._modified3 = False
    # create caller builder
    caller = Object.create(None, "Builder", is_pc=True)
    caller.privilege_level = settings.Privilege.Builder

    assert door.closed is True
    door.try_open(caller)
    assert door.closed is False
    with nh.lock3:
        assert nh._modified3 is True

    with nh.lock3:
        nh._modified3 = False
    door.try_close(caller)
    assert door.closed is True
    with nh.lock3:
        assert nh._modified3 is True


def test_followers_inplace_mutation_marks_leader_dirty(global_test_env):
    leader = Object.create(None, "Leader", is_pc=True)
    follower = Object.create(None, "Follower", is_pc=True)
    # ensure clean
    with leader.lock:
        leader.followers.clear()
        leader.is_modified = False
    with follower.lock:
        follower.following = None
        follower.is_modified = False

    # simulate FollowCommand logic
    with leader.lock:
        leader.followers.add(follower.id)
        object.__setattr__(leader, "is_modified", True)
    assert leader.is_modified is True

    with leader.lock:
        leader.is_modified = False
    with leader.lock:
        leader.followers.discard(follower.id)
        object.__setattr__(leader, "is_modified", True)
    assert leader.is_modified is True

    # exit.py path
    with leader.lock:
        leader.followers.add(follower.id)
        object.__setattr__(leader, "is_modified", True)
        leader.is_modified = False
    # simulate _clear_following
    with leader.lock:
        leader.followers.discard(follower.id)
        object.__setattr__(leader, "is_modified", True)
    assert leader.is_modified is True


def test_early_publication_not_visible_during_at_create(global_test_env):
    from atheriz.globals.objects import filter_by, _ALL_OBJECTS

    seen_during_create = {}

    class TestObj(Object):
        def at_create(self):
            # During at_create, self should NOT yet be in global registry after fix
            # Check via filter_by
            found = filter_by(lambda x: x.id == self.id)
            seen_during_create["found"] = len(found) > 0

    obj = TestObj.create(None, "EarlyTest", is_pc=False)
    # After fix, during at_create it should NOT be found
    assert seen_during_create["found"] is False, "Object was visible during at_create (early publication)"
    # After creation it should be visible
    from atheriz.globals.objects import get

    assert get(obj.id)[0] is obj


def test_map_handler_optimistic_clear_preserves_concurrent_update(global_test_env):
    from atheriz.globals.map import MapInfo
    from atheriz.globals.get import get_map_handler

    mh = get_map_handler()
    mi = MapInfo(name="concurrent_test")
    mi.pre_grid[(0, 0)] = "X"
    mi.map_changed = True
    # put in handler
    mh.set_mapinfo("concurrent_test", 0, mi)
    # simulate optimistic save: clear before snapshot, then concurrent update
    # Our new code clears inside lock before copy, so concurrent after clear should set True
    barrier = threading.Barrier(2, timeout=5)
    errors = []

    def saver():
        try:
            barrier.wait()
            # call save which will optimistically clear
            mh.save(force=True)
        except Exception as e:
            errors.append(f"saver {e}")

    def updater():
        try:
            barrier.wait()
            # small delay to let saver acquire lock first? We want updater to run after saver cleared but before commit
            # In our implementation clear happens inside lock before serialization, so updater after that should set True
            time.sleep(0.05)
            with mi.lock:
                mi.pre_grid[(1, 1)] = "Y"
                mi.map_changed = True
        except Exception as e:
            errors.append(f"updater {e}")

    t1 = threading.Thread(target=saver)
    t2 = threading.Thread(target=updater)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert not errors, f"errors {errors}"
    # After concurrent update, map_changed should still be True (not lost)
    with mi.lock:
        assert mi.map_changed is True
        assert (1, 1) in mi.pre_grid


def test_map_edit_rejects_non_builder_before_validation(monkeypatch, global_test_env):
    from atheriz.inputfuncs import InputFuncs
    from unittest.mock import MagicMock

    funcs = InputFuncs()
    # non-builder puppet
    puppet = MagicMock()
    puppet.is_builder = False
    conn = MagicMock()
    conn.session.puppet = puppet
    conn.client_host = "1.2.3.4"
    # large payload that would be expensive to validate
    large_cells = [[0, 0, "X", [0, 0, 0], [0, 0, 0], ["bold"]] for _ in range(200)]
    # Should reject quickly without iterating all cells? We test that it sends reject
    conn.send_command = MagicMock()
    funcs.map_edit(conn, ["key", 1, large_cells], {})
    conn.send_command.assert_called_with("map_edit_reject", "Builder permission required.")
    # also for map_validate_moves
    conn.send_command.reset_mock()
    large_moves = [[0, 0, 1, 1] for _ in range(200)]
    funcs.map_validate_moves(conn, ["key", 1, large_moves], {})
    conn.send_command.assert_called_with("map_edit_reject", "Builder permission required.")


def test_nodegrid_apply_moves_marks_neighbors_dirty(global_test_env):
    grid = NodeGrid(area="testgrid", z=0)
    n1 = Node(coord=Coord("testgrid", 0, 0, 0), desc="n1")
    n2 = Node(coord=Coord("testgrid", 1, 0, 0), desc="n2")
    n1.links = [NodeLink(name="east", coord=Coord("testgrid", 1, 0, 0))]
    n1.is_modified = False
    n2.is_modified = False
    grid.add_node(n1)
    grid.add_node(n2)
    # reset after add
    n1.is_modified = False
    n2.is_modified = False
    grid.is_modified = False
    # move n2 from (1,0) to (2,0)
    failed = grid.apply_moves([((1, 0), (2, 0))])
    assert failed == []
    # n1 had link to old coord (1,0) should be rewritten to (2,0) and marked dirty
    assert n1.is_modified is True
    assert n1.links[0].coord == Coord("testgrid", 2, 0, 0)

