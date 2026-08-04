"""Issue tests: ChannelCommand lazy channel lookup and channel history slicing.
"""
from __future__ import annotations

import pytest

from atheriz.objects.base_channel import BaseChannelCommand, Channel


class TestBaseChannelCommand:
    def test_channel_property_graceful_when_unset(self, global_test_env):
        """INTENT: accessing `.channel` on a command whose `_channel` was never
        set (e.g. after unpickling) must fall back to the `#id` lookup and
        raise the documented ValueError when the channel is gone — not an
        AttributeError."""
        cmd = BaseChannelCommand()
        cmd.id = 99999  # no such channel
        with pytest.raises(ValueError):
            _ = cmd.channel

    def test_channel_property_roundtrip_after_state_transfer(self, global_test_env):
        """INTENT: after __getstate__/__setstate__ drops `_channel`, the lazy
        fallback must still resolve the channel by id."""
        ch = Channel.create("testchan", None)
        cmd = ch.get_command()
        state = cmd.__getstate__()
        restored = BaseChannelCommand()
        restored.__setstate__(state)
        restored.id = ch.id
        assert restored.channel is ch


class TestChannelHistory:
    def test_get_history_zero_is_empty(self, global_test_env):
        """INTENT: requesting 0 history entries must return nothing. The current
        `list[-0:]` slice returns the entire history instead."""
        ch = Channel.create("testchan", None)
        ch.msg("hello")
        ch.msg("world")
        assert ch.get_history(0) == ""

    def test_get_history_respects_count(self, global_test_env):
        ch = Channel.create("testchan", None)
        ch.msg("one")
        ch.msg("two")
        ch.msg("three")
        out = ch.get_history(1)
        assert "three" in out
        assert "one" not in out
