"""Issue tests: double-counted session playtime on disconnect.

seconds_played is an asymmetric property: the getter adds the live session
delta while the setter writes the raw backing field. at_disconnect() used to
do ``puppet.seconds_played += time.time() - self.conn_time`` while the puppet's
session link was still set, so the read added the delta and the += added it
again — roughly 2x per session, compounding across relogins. The fix clears
the session link before accruing.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from atheriz import database_setup, settings
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import _ALL_OBJECTS, get, load_objects, save_objects


def _make_puppet_with_session(conn_age: float) -> tuple[Object, object]:
    from atheriz.objects.session import Session

    obj = Object.create(None, "Player")
    session = Session(connection=MagicMock())
    session.conn_time = time.time() - conn_age if conn_age > 0 else 0.0
    obj.session = session
    session.puppet = obj
    return obj, session


@pytest.fixture
def no_autosave_on_disconnect(monkeypatch):
    monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)


class TestPlaytimeExactness:
    def test_session_time_counted_once(self, global_test_env, no_autosave_on_disconnect):
        """INTENT: after disconnect, _seconds_played must reflect ~100s of
        session time — not ~200s."""
        obj, session = _make_puppet_with_session(conn_age=100.0)
        assert obj._seconds_played == 0

        session.at_disconnect()

        assert obj._seconds_played == pytest.approx(100.0, abs=2.0)
        assert obj.session is None

    def test_getter_includes_live_delta_while_connected(self, global_test_env):
        """INTENT: display semantics for connected characters are unchanged:
        the property still reports stored + live session time mid-session."""
        obj, _session = _make_puppet_with_session(conn_age=50.0)

        displayed = obj.seconds_played
        assert displayed == pytest.approx(obj._seconds_played + (time.time() - _session.conn_time), abs=1.0)
        assert displayed >= 49.0


class TestDegenerateGuards:
    def test_never_stamped_conn_time_skips_accrual(self, global_test_env, no_autosave_on_disconnect):
        """INTENT: a session that never ran at_connect (conn_time == 0.0) must
        not dump a since-epoch delta into the total."""
        obj, session = _make_puppet_with_session(conn_age=0.0)
        obj._seconds_played = 55.0

        session.at_disconnect()

        assert obj._seconds_played == 55.0

    def test_backwards_clock_does_not_corrupt_total(self, global_test_env, no_autosave_on_disconnect, monkeypatch):
        """INTENT: negative elapsed time (clock stepped back) leaves the total
        untouched instead of subtracting."""
        obj, session = _make_puppet_with_session(conn_age=100.0)
        monkeypatch.setattr(time, "time", lambda: session.conn_time - 5.0)
        obj._seconds_played = 30.0

        session.at_disconnect()

        assert obj._seconds_played == 30.0


class TestPersistence:
    def test_disconnected_total_survives_reload(self, global_test_env, monkeypatch):
        """INTENT: with autosave-on-disconnect enabled, the persisted blob must
        hold the single-counted total."""
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", True)
        obj, session = _make_puppet_with_session(conn_age=100.0)
        save_objects()
        obj._seconds_played = 10.0

        session.at_disconnect()

        expected = obj._seconds_played
        assert expected == pytest.approx(110.0, abs=2.0)

        obj_id = obj.id
        database_setup._DATABASE.close()
        database_setup._CLOSED = False
        _ALL_OBJECTS.clear()
        load_objects()
        reloaded = get(obj_id)
        assert reloaded is not None
        assert reloaded[0]._seconds_played == pytest.approx(expected, abs=2.0)
