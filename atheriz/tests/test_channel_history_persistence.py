"""Regression tests: channel history must be durable.

A broadcast on a channel must mark the channel modified so its history (used
for ``get_history``/replay) survives a server restart. Currently ``Channel.msg``
mutates the ``history`` deque in place, which bypasses the thread-safe
attribute hooks, so a channel that merely relays messages is never re-persisted
and loses its history after a restart.
"""

from atheriz import database_setup
from atheriz.objects.base_channel import Channel
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import get, load_objects, save_objects
import atheriz.settings as settings


def _simulate_restart():
    """Close the database, allow a fresh connection, and reload all objects."""
    database_setup._DATABASE.close()
    database_setup._CLOSED = False
    load_objects()


def test_channel_broadcast_marks_channel_modified(global_test_env):
    channel = Channel.create("announce")
    save_objects()
    assert channel.is_modified is False

    channel.msg("hello there")

    assert channel.is_modified is True


def test_channel_msg_with_sender_marks_modified(global_test_env):
    channel = Channel.create("announce")
    sender = Object.create(None, "S")
    save_objects()
    assert channel.is_modified is False

    channel.msg("hello there", sender)

    assert channel.is_modified is True


def test_channel_history_persists_across_restart(global_test_env):
    channel = Channel.create("announce")
    save_objects()
    channel.msg("hello there")
    channel_id = channel.id

    save_objects()
    _simulate_restart()

    reloaded = get(channel_id)
    assert reloaded is not None
    history = list(reloaded[0].history)
    assert len(history) == 1
    timestamp, sender, message = history[0]
    assert message == "hello there"
    assert sender == ""
    assert isinstance(timestamp, int)
    assert "hello there" in reloaded[0].get_history()


def test_channel_history_cap_survives_restart(global_test_env):
    channel = Channel.create("announce")
    save_objects()
    total = settings.CHANNEL_HISTORY_LIMIT + 5
    for i in range(total):
        channel.msg(f"message {i}")
    channel_id = channel.id

    save_objects()
    _simulate_restart()

    reloaded = get(channel_id)
    history = list(reloaded[0].history)
    assert len(history) == settings.CHANNEL_HISTORY_LIMIT
    assert history[0][2] == f"message {total - settings.CHANNEL_HISTORY_LIMIT}"
    assert history[-1][2] == f"message {total - 1}"


def test_channel_clear_history_marks_modified_and_persists(global_test_env):
    channel = Channel.create("announce")
    save_objects()
    channel.msg("hello there")
    save_objects()
    assert channel.is_modified is False
    channel_id = channel.id

    channel.clear_history()
    assert channel.is_modified is True

    save_objects()
    _simulate_restart()

    reloaded = get(channel_id)
    assert list(reloaded[0].history) == []
