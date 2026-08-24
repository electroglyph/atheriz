"""Issue tests: #11 — `ban --account` only disconnects the *named* character.

`_kick(target, ...)` is only called for the resolved target character; the
account's other online characters get their `is_banned` flag set (ban.py:141-142)
but their sessions stay connected for the rest of the session.

INTENT: banning an account must disconnect every online character of that
account, not just the named one.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from atheriz import settings
from atheriz.commands.loggedin.ban import BanCommand, _find_account
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.tests.fakes import FakeConnection


def _make_caller(privilege=settings.Privilege.Builder):
    c = Object.create(None, "Admin")
    c.privilege_level = privilege
    c.msg = MagicMock()
    return c


def _make_pc(name, privilege=settings.Privilege.Player):
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


def test_ban_account_disconnects_all_online_characters(global_test_env, fixed_salt):
    """INTENT: with ALL characters of the account online, `ban --account` must
    close the connection of every one of them. Today only the named target's
    connection is closed; the sibling stays connected -> FAIL."""
    caller = _make_caller()
    acct = Account.create("acct", "pass12345")
    char_a = _make_pc("Alice")
    char_b = _make_pc("Bob")
    acct.add_character(char_a)
    acct.add_character(char_b)

    conn_a = _attach_connection(char_a, host="10.0.0.1", account=acct)
    conn_b = _attach_connection(char_b, host="10.0.0.2", account=acct)

    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Alice", "--account"]))

    assert conn_a.closed is True, "named target was not kicked"
    assert conn_b.closed is True, "online sibling stayed connected after the account ban"


def test_ban_account_kicks_online_sibling_when_named_offline(global_test_env, fixed_salt):
    """INTENT: even when the *named* character is offline, an online sibling of
    the banned account must be disconnected. Today only the named (offline)
    target reaches `_kick`, which no-ops -- the sibling stays connected."""
    caller = _make_caller()
    acct = Account.create("acct2", "pass12345")
    char_a = _make_pc("Carol")
    char_b = _make_pc("Dave")
    acct.add_character(char_a)
    acct.add_character(char_b)
    conn_b = _attach_connection(char_b, host="10.0.0.3", account=acct)

    assert _find_account(char_a) is acct  # account resolves via scan

    cmd = BanCommand()
    cmd.run(caller, cmd.parser.parse_args(["Carol", "--account"]))

    assert conn_b.closed is True, "online sibling stayed connected after account ban"