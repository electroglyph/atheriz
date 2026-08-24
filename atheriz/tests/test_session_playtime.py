"""Issue tests: `seconds_played` is massively inflated because the connect
flow never stamps `session.conn_time`.

`connect.py`/`guest.py` set the never-read `session.connect_time` attribute,
so `conn_time` stays `0.0` and `Session.at_disconnect` computes
`seconds_played += time.time() - 0.0` (≈ epoch seconds, ~1.7e9).
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from atheriz.commands.unloggedin.connect import ConnectCommand
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.objects.session import Session
from atheriz.tests.fakes import FakeConnection, make_args


class PickFirstSession(Session):
    """A real Session whose character-selection prompt picks the first one."""

    async def prompt(self, text: str) -> str:
        await asyncio.sleep(0)
        return "0"


def _connect(account: Account, char: Object) -> PickFirstSession:
    conn = FakeConnection(session=PickFirstSession())
    cmd = ConnectCommand()
    # at_post_puppet touches channels/session/connection state; mock it at the
    # class level so the mock is never serialized onto the character.
    with patch.object(Object, "at_post_puppet"):
        asyncio.run(cmd.run(conn, make_args(account_name=account.name, password="pw1")))
    return conn.session


class TestSessionPlaytime:
    def test_connect_sets_conn_time(self, global_test_env, fixed_salt):
        """INTENT: the connect command must stamp `session.conn_time` (the field
        `at_disconnect` reads) when a character is selected. It currently sets
        the never-read `session.connect_time` instead, leaving `conn_time` at
        0.0."""
        char = Object.create(None, "hero", is_pc=True)
        account = Account.create("bob", "pw1")
        account.characters = [char.id]

        before = time.time()
        session = _connect(account, char)
        after = time.time()

        assert session.puppet is char
        assert before <= session.conn_time <= after

    def test_disconnect_playtime_is_not_inflated(self, global_test_env, fixed_salt):
        """INTENT: after a real connect flow, disconnecting must reflect the
        actual session length, not `time.time()` (seconds since the epoch)."""
        char = Object.create(None, "hero", is_pc=True)
        account = Account.create("bob", "pw1")
        account.characters = [char.id]

        session = _connect(account, char)
        session.at_disconnect()

        assert char.seconds_played < 60 * 60

    def test_disconnect_persists_final_session_playtime(self, global_test_env, fixed_salt):
        """INTENT: the playtime persisted on disconnect must include the final
        session. `Object.at_disconnect` runs `save_objects()` *before*
        `Session.at_disconnect` adds `time.time() - conn_time` to
        `seconds_played`, so the last session's playtime is never saved."""
        char = Object.create(None, "hero", is_pc=True)
        account = Account.create("bob", "pw1")
        account.characters = [char.id]

        session = _connect(account, char)
        session.conn_time = time.time() - 5.0

        saved_seconds = {}
        with patch("atheriz.objects.base_obj.save_objects") as mock_save:
            mock_save.side_effect = lambda: saved_seconds.update(value=char.seconds_played)
            session.at_disconnect()

        assert mock_save.called
        assert saved_seconds["value"] >= 4.5, (
            "save_objects ran before the final session's playtime was added"
        )
