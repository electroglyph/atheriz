"""Issue tests: Session.conn_time is never set (at_connect is not called), so
`seconds_played` accumulates `time.time()` (seconds since epoch) on disconnect.
"""
from __future__ import annotations

import time

import pytest

from atheriz.objects.base_obj import Object
from atheriz.objects.session import Session


class TestSessionPlaytime:
    def test_disconnect_playtime_is_not_inflated(self, global_test_env):
        """INTENT: on disconnect, the accumulated playtime must reflect the
        actual session length, not `time.time()` (seconds since the epoch).

        A fresh Session starts with conn_time == 0.0 and at_connect() is never
        invoked during the real login flow, so `time.time() - 0.0` inflates the
        playtime to ~1.8e9 seconds.
        """
        obj = Object.create(None, "player", is_pc=True)
        session = Session(connection=object())
        session.puppet = obj
        obj.session = session

        assert session.conn_time == 0.0  # documents the bug trigger

        session.at_disconnect()

        assert obj.seconds_played < 60 * 60
