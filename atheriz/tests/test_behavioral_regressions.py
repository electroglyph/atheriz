import pytest
from unittest.mock import MagicMock


def test_save_ops_preserves_dirty_flag(global_test_env):
    from atheriz.objects.base_obj import Object

    obj = Object.create(None, "m03test")
    obj.is_modified = True
    sql, params = obj.get_save_ops()
    # get_save_ops is intentionally non-clearing (preserves flag); clearing
    # variant is get_save_ops_clearing used by save_objects()
    assert obj.is_modified is True
    assert sql.startswith("INSERT")


def test_save_ops_restores_on_failure(global_test_env, monkeypatch):
    from atheriz.objects.base_obj import Object
    import dill

    obj = Object.create(None, "m03fail")
    obj.is_modified = True
    orig = dill.dumps

    def failing(o):
        raise RuntimeError("boom")

    monkeypatch.setattr(dill, "dumps", failing)
    with pytest.raises(RuntimeError):
        obj.get_save_ops()
    assert obj.is_modified is True
    monkeypatch.setattr(dill, "dumps", orig)


def test_save_ops_clearing_consumes_flag(global_test_env):
    from atheriz.objects.base_obj import Object

    obj = Object.create(None, "m03clear")
    obj.is_modified = True
    obj.get_save_ops_clearing()
    assert obj.is_modified is False


def test_every_minute_alarm_fires(global_test_env, monkeypatch):
    from atheriz.globals.get import get_game_time
    from atheriz.objects.base_obj import Object
    from unittest.mock import MagicMock

    gt = get_game_time()
    obj = Object.create(None, "m05obj")
    called = []

    def at_alarm(t, d):
        called.append(t)

    obj.at_alarm = at_alarm
    with gt.lock:
        gt.ticks = 0
        gt.alarms.clear()
    gt.add_alarm("?", "?", obj, repeat=False, data={"x": 1})
    mock_atp = MagicMock()

    def immediate(func, *a, **kw):
        func(*a, **kw)
        return True

    mock_atp.add_task.side_effect = immediate
    monkeypatch.setattr("atheriz.globals.time.get_async_threadpool", lambda: mock_atp)
    gt.on_tick()
    assert len(called) == 1
    with gt.lock:
        assert ("?", "?") not in gt.alarms or not gt.alarms.get(("?", "?"))


def test_every_minute_alarm_repeats_when_repeat(global_test_env, monkeypatch):
    from atheriz.globals.get import get_game_time
    from atheriz.objects.base_obj import Object
    from unittest.mock import MagicMock

    gt = get_game_time()
    obj = Object.create(None, "m05rep")
    called = []

    def at_alarm(t, d):
        called.append(1)

    obj.at_alarm = at_alarm
    with gt.lock:
        gt.ticks = 0
        gt.alarms.clear()
    gt.add_alarm("?", "?", obj, repeat=True)
    mock_atp = MagicMock()

    def immediate(func, *a, **kw):
        func(*a, **kw)
        return True

    mock_atp.add_task.side_effect = immediate
    monkeypatch.setattr("atheriz.globals.time.get_async_threadpool", lambda: mock_atp)
    gt.on_tick()
    gt.on_tick()
    assert len(called) == 2
    with gt.lock:
        assert ("?", "?") in gt.alarms


def test_install_hooks_only_decorated(global_test_env):
    from atheriz.objects.base_script import Script, before
    from atheriz.coord import Coord
    from atheriz.objects.nodes import Node

    class MyScript(Script):
        @before
        def at_tick(self):
            pass

        def at_install(self):
            pass

        def at_custom_helper(self):
            pass

    s = MyScript.create(None, "m08script")
    node = Node(coord=Coord("TestA", 0, 0, 0))
    with node.lock:
        node.hooks.clear()
    s.install_hooks(node)
    with node.lock:
        assert "at_tick" in node.hooks
        assert "at_install" not in node.hooks
        assert "at_custom_helper" not in node.hooks
    s.remove_hooks(node)
    with node.lock:
        assert "at_tick" not in node.hooks or len(node.hooks.get("at_tick", [])) == 0


def test_help_exits_via_command_error(global_test_env):
    from atheriz.commands.base_cmd import GameArgumentParser, CommandError

    p = GameArgumentParser(prog="test", add_help=True)
    p.add_argument("--foo", help="foo")
    with pytest.raises(CommandError):
        p.parse_args(["--help"])
    # exit with no message is silent (original contract)
    p.exit(0, None)
    with pytest.raises(CommandError) as e:
        p.exit(1, "oops")
    assert "oops" in str(e.value)


def test_print_help_without_parser_returns_aliases(global_test_env):
    from atheriz.commands.base_cmd import Command

    class NoParserCmd(Command):
        key = "nop"
        aliases = ["np", "n"]
        use_parser = False
        extra_desc = "extra"

    c = NoParserCmd()
    out = c.print_help()
    assert "nop" in out
    assert "extra" in out
    assert "np" in out


def test_print_help_with_parser_still_works(global_test_env):
    from atheriz.commands.base_cmd import Command

    class WithParser(Command):
        key = "withp"
        desc = "desc"
        use_parser = True

        def setup_parser(self):
            self.parser.add_argument("target")

    c = WithParser()
    out = c.print_help()
    assert "withp" in out
    assert "target" in out


def test_pad_accounts_for_wide_chars(global_test_env):
    from atheriz.objects.funcparser_helpers import pad, m_len

    assert m_len("漢") == 2
    result = pad("漢", width=4, align="l")
    assert m_len(result) == 4
    assert result.startswith("漢")
    assert result == "漢  "
    result_c = pad("漢", width=4, align="c")
    assert m_len(result_c) == 4
    assert "漢" in result_c
    result2 = pad("漢字", width=3, align="l")
    assert result2 == "漢字"


def test_crop_accounts_for_wide_chars(global_test_env):
    from atheriz.objects.funcparser_helpers import crop, m_len

    assert m_len("漢字") == 4
    result = crop("漢字漢字", width=3, suffix="...")
    assert m_len(result) <= 3
    result2 = crop("a" * 100, width=10, suffix="...")
    assert len(result2) == 10
    assert result2.endswith("...")
    result3 = crop("hi", width=10)
    assert result3 == "hi"


def test_astar_no_stale_start_entry(global_test_env):
    from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
    from atheriz.utils import Coord
    from unittest.mock import patch, MagicMock
    from atheriz.globals.node import NodeHandler
    from atheriz.pathfind import astar

    class MockMapInfo:
        def __init__(self):
            self.lock = MagicMock()
            self.post_grid = {}
            self.pre_grid = None
            self.map_changed = False

        def update_grid(self, coord, symbol):
            pass

        def render(self, force=False):
            pass

    class MockMapHandler:
        def get_mapinfo(self, area, z):
            return MockMapInfo()

    nh = NodeHandler()
    with patch("atheriz.pathfind.get_node_handler", return_value=nh), patch(
        "atheriz.objects.nodes.get_node_handler", return_value=nh
    ), patch("atheriz.globals.node.get_map_handler", return_value=MockMapHandler()):
        area = NodeArea(name="AstarA")
        grid = NodeGrid(area="AstarA", z=0)
        coord_a = Coord("AstarA", 0, 0, 0)
        coord_b = Coord("AstarA", 1, 0, 0)
        node_a = Node(coord=coord_a)
        node_b = Node(coord=coord_b)
        node_a.links = [NodeLink("east", coord_b)]
        node_b.links = [NodeLink("west", coord_a)]
        grid.nodes[(0, 0)] = node_a
        grid.nodes[(1, 0)] = node_b
        area.add_grid(grid)
        nh.add_area(area)

        ok, path, closed = astar(node_a, node_b)
        assert ok is True
        assert path[0].coord == coord_a
        assert path[-1].coord == coord_b
        ok2, path2, _ = astar(node_a, node_a)
        assert ok2 is True


def test_social_unknown_target_messages_player(global_test_env):
    from atheriz.commands.loggedin.socials import CmdSocials
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node
    from atheriz.utils import Coord

    room = Node(coord=Coord("SocialA", 0, 0, 0))
    caller = Object.create(None, "SocialCaller")
    caller.move_to(room)
    cmd = CmdSocials()
    args = MagicMock()
    args.cmdstring = "smile"
    args.target = ["nonexistent_xyz"]
    msgs = []
    caller.msg = lambda x: msgs.append(x)
    cmd.run(caller, args)
    assert any("Could not find" in m for m in msgs)


def test_social_known_target_still_works(global_test_env):
    from atheriz.commands.loggedin.socials import CmdSocials
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node
    from atheriz.utils import Coord

    room = Node(coord=Coord("SocialB", 0, 0, 0))
    caller = Object.create(None, "SocialCaller2")
    target = Object.create(None, "TargetBob")
    caller.move_to(room)
    target.move_to(caller)

    cmd = CmdSocials()
    args = MagicMock()
    args.cmdstring = "smile"
    args.target = ["TargetBob"]
    msgs = []
    caller.msg = lambda x: msgs.append(x)
    orig = room.msg_contents
    room_msgs = []
    room.msg_contents = lambda *a, **kw: room_msgs.append(a)
    cmd.run(caller, args)
    room.msg_contents = orig
    assert not any("Could not find" in m for m in msgs)
    assert len(room_msgs) == 1


def test_connection_screen_reflects_runtime_toggle(global_test_env, monkeypatch):
    import atheriz.settings as settings
    import atheriz.connection_screen as cs

    monkeypatch.setattr(settings, "GUEST_ENABLED", True)
    monkeypatch.setattr(settings, "ACCOUNT_CREATION_ENABLED", True)
    out1 = cs.render()
    assert "guest" in out1.lower()
    assert "create" in out1.lower()

    monkeypatch.setattr(settings, "GUEST_ENABLED", False)
    out2 = cs.render()
    assert "guest" not in out2.lower()

    monkeypatch.setattr(settings, "ACCOUNT_CREATION_ENABLED", False)
    out3 = cs.render()
    assert "create" not in out3.lower()


def test_unlock_when_already_unlocked_reports_failure(global_test_env):
    from atheriz.objects.base_door import Door
    from atheriz.utils import Coord
    from atheriz.objects.nodes import Node
    from atheriz.objects.base_obj import Object

    from_coord = Coord("DoorA", 0, 0, 0)
    to_coord = Coord("DoorA", 1, 0, 0)
    room = Node(coord=from_coord)
    caller = Object.create(None, "DoorCaller")
    caller.location = room
    door = Door(
        from_coord=from_coord,
        from_exit="east",
        to_coord=to_coord,
        to_exit="west",
        closed=False,
        locked=False,
    )
    door.add_lock("unlock", lambda o: True)
    msgs = []
    room.msg_contents = lambda *a, **kw: msgs.append(" ".join(str(x) for x in a) + str(kw))
    result = door.try_unlock(caller)
    assert result is False
    assert any("already unlocked" in m for m in msgs)

    door.locked = True
    msgs.clear()
    result2 = door.try_unlock(caller)
    assert result2 is True
    assert door.locked is False


def test_try_lock_already_locked_symmetry(global_test_env):
    from atheriz.objects.base_door import Door
    from atheriz.utils import Coord
    from atheriz.objects.nodes import Node
    from atheriz.objects.base_obj import Object

    from_coord = Coord("DoorB", 0, 0, 0)
    to_coord = Coord("DoorB", 1, 0, 0)
    room = Node(coord=from_coord)
    caller = Object.create(None, "DoorCaller2")
    caller.location = room
    door = Door(from_coord=from_coord, from_exit="east", to_coord=to_coord, to_exit="west", locked=True)
    door.add_lock("lock", lambda o: True)
    msgs = []
    room.msg_contents = lambda *a, **kw: msgs.append("".join(str(x) for x in a))
    result = door.try_lock(caller)
    assert result is False
    assert any("already locked" in m for m in msgs)


def test_help_hides_guest_when_disabled(global_test_env, monkeypatch):
    import atheriz.settings as settings
    from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet

    monkeypatch.setattr(settings, "GUEST_ENABLED", False)
    monkeypatch.setattr(settings, "ACCOUNT_CREATION_ENABLED", True)
    monkeypatch.setattr(settings, "CHAR_CREATION_ENABLED", True)
    cs = UnloggedinCmdSet()
    assert cs.get("guest") is None
    assert "guest" not in [k.lower() for k in cs.get_keys()]

    monkeypatch.setattr(settings, "GUEST_ENABLED", True)
    cs2 = UnloggedinCmdSet()
    assert cs2.get("guest") is not None


def test_account_name_case_insensitive_unique(global_test_env):
    from atheriz.objects.base_account import Account

    a1 = Account.create("Alice", "hunter22")
    assert a1 is not None
    with pytest.raises(ValueError) as e:
        Account.create("alice", "hunter23")
    assert "already exists" in str(e.value)
    with pytest.raises(ValueError):
        Account.create("ALICE", "hunter24")


def test_account_login_case_insensitive(global_test_env):
    from atheriz.objects.base_account import Account

    a = Account.create("BobCase", "hunter22")
    assert a.login("bobcase", "hunter22") is True
    assert a.login("BOBCASE", "hunter22") is True
    assert a.login("Alice", "hunter22") is False


def test_salt_file_utf8_roundtrip(global_test_env, monkeypatch, tmp_path):
    import atheriz.settings as settings
    from pathlib import Path
    from atheriz.globals import salt as salt_mod

    monkeypatch.setattr(settings, "SECRET_PATH", str(tmp_path / "secret"))
    monkeypatch.setattr("atheriz.utils.is_in_game_folder", lambda: True)
    salt_mod._SALT = None
    p = Path(settings.SECRET_PATH) / "salt.txt"
    from atheriz.globals.salt import get_salt

    s = get_salt()
    assert s is not None
    content = p.read_text(encoding="utf-8")
    assert content.strip() == s
    salt_mod._SALT = None
    s2 = get_salt()
    assert s2 == s


def test_channel_name_case_insensitive_unique(global_test_env):
    from atheriz.objects.base_channel import Channel

    c1 = Channel.create("General", None)
    assert c1.name == "General"
    with pytest.raises(ValueError):
        Channel.create("general", None)
    with pytest.raises(ValueError):
        Channel.create("GENERAL", None)
    from atheriz.globals.objects import filter_by

    results = filter_by(lambda x: getattr(x, "is_channel", False) and x.name.lower() == "general")
    assert len(results) == 1
    assert results[0].id == c1.id
