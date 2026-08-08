"""Regression tests: channel history must be durable.

A broadcast on a channel must mark the channel modified so its history (used
for ``get_history``/replay) survives a server restart. Currently ``Channel.msg``
mutates the ``history`` deque in place, which bypasses the thread-safe
attribute hooks, so a channel that merely relays messages is never re-persisted
and loses its history after a restart.
"""

from atheriz import database_setup
from atheriz.objects.base_channel import Channel
from atheriz.globals.objects import get, load_objects, save_objects


def test_channel_broadcast_marks_channel_modified(global_test_env):
    channel = Channel.create("announce")
    save_objects()
    assert channel.is_modified is False

    channel.msg("hello there")

    assert channel.is_modified is True


def test_channel_history_persists_across_restart(global_test_env):
    channel = Channel.create("announce")
    save_objects()
    channel.msg("hello there")
    channel_id = channel.id

    save_objects()
    database_setup._DATABASE.close()
    load_objects()

    reloaded = get(channel_id)
    assert reloaded is not None
    assert len(list(reloaded[0].history)) == 1