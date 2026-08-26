"""Issue tests: ChannelCommand shared-state races on the singleton cmdset.

`get_loggedin_cmdset()` returns a process-wide singleton whose command
instances are shared by every logged-in player. `ChannelCommand` used to store
the selected channel on the instance (`self.channel`/`self.id`), so two
concurrent invocations could clobber each other's target, and the class-level
`_channel_cache` never dropped deleted channels, so a deleted channel stayed
cached forever.
"""
from __future__ import annotations

import threading

import pytest

from atheriz.commands.loggedin.channel import ChannelCommand
from atheriz.objects.base_channel import Channel
from atheriz.tests.fakes import MockCaller, make_args


class TestChannelCommandRace:
    def setup_method(self):
        ChannelCommand._channel_cache.clear()

    def _caller(self, name):
        caller = MockCaller(name=name)
        caller.is_superuser = False
        return caller

    def test_concurrent_invocations_use_their_own_target(self, global_test_env):
        """INTENT: when two players run `channel` concurrently on the shared
        singleton command, each must subscribe to the channel they chose, not
        the one the other player selected. `Barrier(2)` forces the race on the
        shared `_channel_cache` and the former `self.channel` mutation."""
        chan_a = Channel.create("alpha")
        chan_b = Channel.create("beta")
        caller_a = self._caller("Alice")
        caller_b = self._caller("Bob")

        cmd = ChannelCommand()
        barrier = threading.Barrier(2, timeout=5)

        def run_a():
            barrier.wait(timeout=5)
            cmd.run(caller_a, make_args(channel="alpha", subscribe=True))

        def run_b():
            barrier.wait(timeout=5)
            cmd.run(caller_b, make_args(channel="beta", subscribe=True))

        t_a = threading.Thread(target=run_a)
        t_b = threading.Thread(target=run_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=5)
        t_b.join(timeout=5)

        assert not t_a.is_alive() and not t_b.is_alive(), "invocations hung"
        caller_a.subscribe.assert_called_once_with(chan_a)
        caller_b.subscribe.assert_called_once_with(chan_b)

    def test_stale_cached_channel_rejected_after_delete(self, global_test_env):
        """INTENT: after a channel is deleted, the shared cache must not hand
        the deleted channel back out; the command must report it missing."""
        chan = Channel.create("stalechan")
        caller = self._caller("Carol")
        cmd = ChannelCommand()

        args = make_args(channel="stalechan", message="hello")
        cmd.run(caller, args)
        assert chan in ChannelCommand._channel_cache.values()

        chan.delete()
        cmd.run(caller, args)

        messages = [str(c.args[0]) for c in caller.msg.call_args_list]
        assert any("stalechan not found" in m for m in messages), messages


class TestChannelDeleteSubscribeRace:
    def test_channel_delete_blocks_concurrent_subscribe(self, global_test_env):
        """INTENT: add_listener checks is_deleted outside lock then inserts after
        clear, so concurrent delete + subscribe can leave listener in deleted
        channel. Correct code checks is_deleted inside lock."""
        import inspect
        from atheriz.objects.base_channel import Channel

        src = inspect.getsource(Channel.add_listener)
        lines = src.splitlines()
        lock_idx = next((i for i, l in enumerate(lines) if "with self.lock" in l), None)
        check_idx = next((i for i, l in enumerate(lines) if "is_deleted" in l), None)
        assert lock_idx is not None and check_idx is not None
        assert lock_idx < check_idx, "add_listener must check is_deleted inside lock to avoid delete/subscribe race"

    def test_channel_delete_leaves_no_listener_in_deleted_channel(self, global_test_env):
        """INTENT: delete sets is_deleted and clears listeners in separate
        lock blocks, allowing add_listener to slip in between. Correct code
        holds one lock across both."""
        import inspect
        from atheriz.objects.base_channel import Channel

        src = inspect.getsource(Channel.delete)
        assert src.count("with self.lock:") == 1, "delete must hold single lock across is_deleted and listeners clear to avoid race"
