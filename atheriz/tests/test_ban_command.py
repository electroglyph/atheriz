from unittest.mock import MagicMock

from atheriz.commands.loggedin.ban import BanCommand, UnbanCommand
from atheriz.globals.objects import TEMP_BANNED_IPS, _ALL_OBJECTS
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz import settings
from atheriz.tests.fakes import FakeConnection
from atheriz.utils import strip_ansi


def _make_caller(privilege=settings.Privilege.Builder):
    c = Object.create(None, "Admin")
    c.privilege_level = privilege
    c.msg = MagicMock()
    return c


def _make_pc(name="Bob", privilege=settings.Privilege.Player):
    pc = Object.create(None, name)
    pc.is_pc = True
    pc.privilege_level = privilege
    return pc


def _attach_connection(pc, host="1.2.3.4", account=None):
    conn = FakeConnection(session_id=f"conn-{pc.id}")
    conn.client_host = host
    pc.session = conn.session
    conn.session.puppet = pc
    if account is not None:
        conn.session.account = account
    return conn


def _last_msg(mock):
    return strip_ansi(mock.msg.call_args[0][0])


# --- access control ---------------------------------------------------------


def test_access_denied_for_non_builder():
    cmd = BanCommand()
    c = _make_caller()
    c.privilege_level = settings.Privilege.Player
    assert cmd.access(c) is False


def test_access_granted_for_builder():
    cmd = BanCommand()
    assert cmd.access(_make_caller()) is True


def test_unban_access_denied_for_non_builder():
    cmd = UnbanCommand()
    c = _make_caller()
    c.privilege_level = settings.Privilege.Player
    assert cmd.access(c) is False


# --- privilege gate ---------------------------------------------------------


def test_cannot_ban_equal_privilege():
    caller = _make_caller(settings.Privilege.Builder)
    target = _make_pc("Rival", settings.Privilege.Builder)
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Rival"]))
    assert target.is_banned is False
    assert "equal or higher" in _last_msg(caller)


def test_cannot_ban_higher_privilege():
    caller = _make_caller(settings.Privilege.Builder)
    target = _make_pc("Boss", settings.Privilege.Admin)
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Boss"]))
    assert target.is_banned is False
    assert "equal or higher" in _last_msg(caller)


def test_builder_can_ban_player():
    caller = _make_caller(settings.Privilege.Builder)
    target = _make_pc("Newbie", settings.Privilege.Player)
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Newbie"]))
    assert target.is_banned is True


# --- character-only ban -----------------------------------------------------


def test_ban_character_sets_flag():
    caller = _make_caller()
    target = _make_pc("Chuck")
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Chuck"]))
    assert target.is_banned is True
    assert "ban_reason" not in vars(target)


def test_ban_character_with_reason():
    caller = _make_caller()
    target = _make_pc("Chuck")
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Chuck", "-r", "spamming"]))
    assert target.is_banned is True
    assert target.ban_reason == "spamming"


def test_ban_by_id():
    caller = _make_caller()
    target = _make_pc("Chuck")
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args([f"#{target.id}"]))
    assert target.is_banned is True


def test_ban_npc_rejected():
    caller = _make_caller()
    npc = Object.create(None, "Goblin")  # is_pc stays False
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args([f"#{npc.id}"]))
    assert npc.is_banned is False
    assert "player characters" in _last_msg(caller)


def test_ban_no_match():
    caller = _make_caller()
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Ghost"]))
    assert "No player character" in _last_msg(caller)


# --- account ban ------------------------------------------------------------


def test_ban_account_propagates_to_all_characters():
    caller = _make_caller()
    acct = Account.create("acct1", "pass12345")
    char_a = _make_pc("Alice")
    char_b = _make_pc("Bob")
    acct.add_character(char_a)
    acct.add_character(char_b)

    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Alice", "--account", "-r", "toxic"]))

    assert acct.is_banned is True
    assert acct.ban_reason == "toxic"
    assert char_a.is_banned is True
    assert char_b.is_banned is True
    assert char_a.ban_reason == "toxic"
    assert char_b.ban_reason == "toxic"


def test_ban_account_offline_target_resolves():
    caller = _make_caller()
    acct = Account.create("acct2", "pass12345")
    char = _make_pc("Offline")
    acct.add_character(char)

    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Offline", "--account"]))

    assert acct.is_banned is True
    assert char.is_banned is True


def test_ban_account_no_account_falls_back_to_character():
    caller = _make_caller()
    orphan = _make_pc("Orphan")  # no account owns it
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Orphan", "--account"]))
    assert orphan.is_banned is True
    # warning fires first, then the success message reflects character scope
    sent = [strip_ansi(c[0][0]) for c in caller.msg.call_args_list]
    assert any("character only" in m for m in sent)
    assert "(character)" in sent[-1]


# --- IP ban -----------------------------------------------------------------


def test_ban_ip_online_target():
    caller = _make_caller()
    target = _make_pc("Online")
    _attach_connection(target, host="9.9.9.9")
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Online", "--ip"]))
    assert TEMP_BANNED_IPS.get("9.9.9.9") == float("inf")


def test_ban_ip_offline_target_warns():
    caller = _make_caller()
    target = _make_pc("Offline")
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Offline", "--ip"]))
    sent = [strip_ansi(c[0][0]) for c in caller.msg.call_args_list]
    assert any("cannot ban IP" in m for m in sent)
    assert TEMP_BANNED_IPS == {}


def test_ban_kicks_connected_target():
    caller = _make_caller()
    target = _make_pc("Connected")
    conn = _attach_connection(target)
    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Connected"]))
    assert conn.closed is True


# --- unban ------------------------------------------------------------------


def test_unban_character_clears_flag():
    caller = _make_caller()
    target = _make_pc("Chuck")
    target.is_banned = True
    setattr(target, "ban_reason", "x")
    cmd = UnbanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Chuck"]))
    assert target.is_banned is False
    assert "ban_reason" not in vars(target)


def test_unban_account_clears_all():
    caller = _make_caller()
    acct = Account.create("acct3", "pass12345")
    char_a = _make_pc("A")
    char_b = _make_pc("B")
    acct.add_character(char_a)
    acct.add_character(char_b)
    acct.is_banned = True
    char_a.is_banned = True
    char_b.is_banned = True
    setattr(char_a, "ban_reason", "x")

    cmd = UnbanCommand()
    cmd.run(caller, cmd.parser.parse_args(["A", "--account"]))

    assert acct.is_banned is False
    assert acct.ban_reason == ""
    assert char_a.is_banned is False
    assert char_b.is_banned is False
    assert "ban_reason" not in vars(char_a)


def test_unban_ip_clears_entry():
    caller = _make_caller()
    target = _make_pc("Online")
    _attach_connection(target, host="5.5.5.5")
    TEMP_BANNED_IPS["5.5.5.5"] = float("inf")
    cmd = UnbanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Online", "--ip"]))
    assert "5.5.5.5" not in TEMP_BANNED_IPS


def test_unban_privilege_gate():
    caller = _make_caller(settings.Privilege.Builder)
    target = _make_pc("Rival", settings.Privilege.Builder)
    target.is_banned = True
    cmd = UnbanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Rival"]))
    assert target.is_banned is True
    assert "equal or higher" in _last_msg(caller)
