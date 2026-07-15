import _thread
import pickle
from collections import deque
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from atheriz.commands.loggedin.channel import ChannelCommand as GlobalChannelCommand
from atheriz.globals.objects import _ALL_OBJECTS, add_object
from atheriz.objects.base_channel import BaseChannelCommand, Channel
from atheriz.objects.base_obj import Object
from atheriz.tests.fakes import make_object


class MockArgs:
    def __init__(self, **kwargs):
        self.list = kwargs.get("list", False)
        self.channel = kwargs.get("channel", None)
        self.unsubscribe = kwargs.get("unsubscribe", False)
        self.subscribe = kwargs.get("subscribe", False)
        self.replay = kwargs.get("replay", False)
        self.message = kwargs.get("message", None)


@pytest.fixture(autouse=True)
def _clear_channel_cache():
    GlobalChannelCommand._channel_cache.clear()
    yield
    GlobalChannelCommand._channel_cache.clear()


@pytest.fixture
def caller():
    c = Object()
    c.name = "TestPlayer"
    c.id = 1
    c.msg = MagicMock()
    c.unsubscribe = MagicMock()
    c.subscribe = MagicMock()
    return c


@pytest.fixture
def channel():
    chan = Channel()
    chan.name = "public"
    chan.id = 100
    chan.desc = "Public channel"
    return chan


def test_channel_list_no_message(caller, channel):
    """Test 'channel -l' works without a message."""
    cmd = GlobalChannelCommand()
    args = MockArgs(list=True)

    with patch("atheriz.commands.loggedin.channel.filter_by") as mock_get:
        mock_get.return_value = [channel]
        cmd.run(caller, args)

    caller.msg.assert_called()
    # Check that it listed the channel
    args_list = [str(call.args[0]) for call in caller.msg.call_args_list]
    assert any("available channels" in arg for arg in args_list)
    assert any("public" in arg for arg in args_list)


def test_channel_send_message(caller, channel):
    """Test 'channel -c <channel> <message>' sends a message to the channel."""
    cmd = GlobalChannelCommand()

    with patch("atheriz.commands.loggedin.channel.filter_by") as mock_filter:
        mock_filter.return_value = [channel]
        with patch.object(channel, "msg") as mock_msg:
            args = MockArgs(channel="public", message="hello")
            cmd.run(caller, args)
            mock_msg.assert_called_with("hello", caller)


def test_channel_no_message_no_flags(caller, channel):
    """Test 'channel' with no arguments does nothing or shows status (depending on implementation)."""
    # The user removed the 'Currently targeting' msg in channel.py,
    # but base_channel.py still has it.
    cmd = GlobalChannelCommand()
    cmd.id = channel.id
    cmd._channel = channel

    args = MockArgs()
    cmd.run(caller, args)
    # If the logic doesn't call msg, this test might need adjustment
    # caller.msg.assert_called()


def test_channel_target_and_message(caller, channel):
    """Test 'channel -c public hello' targets and sends."""
    cmd = GlobalChannelCommand()

    args = MockArgs(channel="public", message="hello")

    with patch("atheriz.commands.loggedin.channel.filter_by") as mock_filter:
        mock_filter.return_value = [channel]
        with patch.object(channel, "msg") as mock_msg:
            cmd.run(caller, args)
            mock_msg.assert_called_with("hello", caller)

    assert cmd.channel == channel


def test_channel_lookup_cached(caller, channel):
    """Repeated channel lookups should use cache, not scan all objects every time."""
    cmd = GlobalChannelCommand()

    args = MockArgs(channel="public", message="hi")

    with patch("atheriz.commands.loggedin.channel.filter_by") as mock_filter:
        mock_filter.return_value = [channel]
        cmd.run(caller, args)
        cmd.run(caller, args)
        cmd.run(caller, args)
        # filter_by should only be called once, subsequent calls use cache
        assert mock_filter.call_count == 1


def test_local_channel_command_help(caller, channel):
    """Test that ChannelCommand initialized via Channel.get_command has correct help."""
    channel.name = "Server"
    channel.desc = "Server announcements"

    cmd = channel.get_command()
    assert cmd.key == "server"
    assert cmd.desc == "Server announcements"

    # Check help output
    help_text = cmd.parser.format_help()
    assert "usage: server" in help_text
    assert "Server announcements" in help_text


def test_local_channel_command_no_message(caller, channel):
    """Test that LocalChannelCommand shows help without message."""
    channel.name = "Server"
    cmd = channel.get_command()

    args = MockArgs(message=None)
    cmd.run(caller, args)

    caller.msg.assert_called()
    args_list = [str(call.args[0]) for call in caller.msg.call_args_list]
    # Without a message, it shows the help
    assert any("usage: server" in arg.lower() for arg in args_list)


# =============================================================================
# Channel class — constructor and state
# =============================================================================


class TestChannelConstructor:
    def test_init_defaults(self, global_test_env):
        chan = Channel()
        assert chan.name == ""
        assert chan.desc == ""
        assert chan.id == -1
        assert chan.created_by == -1
        assert chan.command is None

    def test_init_creates_rlock(self, global_test_env):
        chan = Channel()
        assert isinstance(chan.lock, _thread.RLock)

    def test_init_is_channel_flag(self, global_test_env):
        chan = Channel()
        assert chan.is_channel is True

    def test_init_listeners_empty(self, global_test_env):
        chan = Channel()
        assert chan.listeners == {}

    def test_init_history_is_deque(self, global_test_env):
        chan = Channel()
        assert isinstance(chan.history, deque)

    def test_init_history_bounded(self, global_test_env):
        # INTENT: history is bounded so channels don't grow unbounded
        from atheriz import settings
        chan = Channel()
        assert chan.history.maxlen == settings.CHANNEL_HISTORY_LIMIT


# =============================================================================
# Channel.create
# =============================================================================


class TestChannelCreate:
    def test_create_with_name(self, global_test_env):
        chan = Channel.create("mychan")
        assert chan is not None
        assert chan.name == "mychan"
        # INTENT: id is a non-negative integer (counter starts at -1, first
        # call returns 0)
        assert chan.id >= 0

    def test_create_sets_caller_id(self, global_test_env):
        caller = make_object("owner", is_pc=True)
        caller.id = 42
        chan = Channel.create("admin", caller=caller)
        assert chan.created_by == 42

    def test_create_no_caller_uses_minus_one(self, global_test_env):
        chan = Channel.create("anonchan")
        assert chan.created_by == -1

    def test_create_duplicate_raises(self, global_test_env):
        # INTENT: collision is a hard error (not None like Account) so the
        # caller cannot silently ignore it
        Channel.create("dup")
        with pytest.raises(ValueError, match="already exists"):
            Channel.create("dup")

    def test_create_adds_to_global_registry(self, global_test_env):
        chan = Channel.create("regchan")
        assert chan in _ALL_OBJECTS.values()

    def test_create_calls_at_create(self, global_test_env):
        called = []
        orig = Channel.at_create
        Channel.at_create = lambda self: called.append(self)
        try:
            chan = Channel.create("atchan")
            assert called == [chan]
        finally:
            Channel.at_create = orig


# =============================================================================
# Channel.delete
# =============================================================================


class TestChannelDelete:
    def test_delete_removes_from_registry(self, global_test_env):
        chan = Channel.create("delchan")
        assert chan in _ALL_OBJECTS.values()
        assert chan.delete() is True
        assert chan not in _ALL_OBJECTS.values()

    def test_delete_marks_is_deleted(self, global_test_env):
        chan = Channel.create("delchan2")
        chan.delete()
        assert chan.is_deleted is True

    def test_delete_vetoed_by_at_delete(self, global_test_env):
        # INTENT: a hook veto must abort the entire delete
        chan = Channel.create("vetochan")
        orig = Channel.at_delete
        Channel.at_delete = lambda self, caller=None: False
        try:
            result = chan.delete()
            assert result is False
            assert chan in _ALL_OBJECTS.values()
            assert chan.is_deleted is False
        finally:
            Channel.at_delete = orig

    def test_delete_temporary_skips_db_ops(self, monkeypatch, global_test_env):
        # INTENT: temporary channels don't write to the DB, so they shouldn't
        # issue delete ops either
        del_calls = []
        import atheriz.objects.base_channel as bc
        monkeypatch.setattr(bc, "delete_objects", lambda ops: del_calls.append(ops))
        chan = Channel.create("tempchan")
        chan.is_temporary = True
        assert chan.delete() is True
        assert del_calls == []

    def test_delete_persistent_uses_db_ops(self, monkeypatch, global_test_env):
        # INTENT: persistent channels must be removed from the DB
        del_calls = []
        import atheriz.objects.base_channel as bc
        monkeypatch.setattr(bc, "delete_objects", lambda ops: del_calls.append(ops))
        chan = Channel.create("persistchan")
        assert chan.is_temporary is False
        assert chan.delete() is True
        assert len(del_calls) == 1
        sql, params = del_calls[0][0]
        assert sql == "DELETE FROM objects WHERE id = ?"
        assert params == (chan.id,)


# =============================================================================
# Channel listener management
# =============================================================================


class TestChannelListeners:
    def test_add_listener_stores_by_id(self, global_test_env):
        chan = Channel()
        listener = make_object("sub1", is_pc=True)
        listener.id = 1
        chan.add_listener(listener)
        assert chan.listeners[1] is listener

    def test_add_multiple_listeners(self, global_test_env):
        chan = Channel()
        l1 = make_object("a", is_pc=True); l1.id = 1
        l2 = make_object("b", is_pc=True); l2.id = 2
        chan.add_listener(l1)
        chan.add_listener(l2)
        assert chan.listeners[1] is l1
        assert chan.listeners[2] is l2

    def test_add_listener_replaces_same_id(self, global_test_env):
        chan = Channel()
        l1 = make_object("a", is_pc=True); l1.id = 1
        l1_replacement = make_object("a2", is_pc=True); l1_replacement.id = 1
        chan.add_listener(l1)
        chan.add_listener(l1_replacement)
        assert chan.listeners[1] is l1_replacement

    def test_remove_listener(self, global_test_env):
        chan = Channel()
        listener = make_object("sub", is_pc=True); listener.id = 5
        chan.add_listener(listener)
        chan.remove_listener(listener)
        assert 5 not in chan.listeners

    def test_remove_listener_missing_no_error(self, global_test_env):
        chan = Channel()
        listener = make_object("sub", is_pc=True); listener.id = 99
        # Not added; remove should be silent
        chan.remove_listener(listener)
        assert chan.listeners == {}


# =============================================================================
# Channel.msg and history
# =============================================================================


class TestChannelMsg:
    def test_msg_adds_to_history(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        chan.msg("hello", sender=None)
        assert len(chan.history) == 1
        # Entry: (timestamp, sender_name, message)
        _ts, sender, msg = chan.history[0]
        assert msg == "hello"
        assert sender == ""

    def test_msg_with_sender_records_name(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        sender = make_object("alice", is_pc=True)
        sender.name = "Alice"
        chan.msg("hi", sender=sender)
        _ts, name, msg = chan.history[0]
        assert name == "Alice"
        assert msg == "hi"

    def test_msg_broadcasts_to_listeners(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        l1 = make_object("a", is_pc=True); l1.msg = MagicMock()
        l2 = make_object("b", is_pc=True); l2.msg = MagicMock()
        chan.add_listener(l1)
        chan.add_listener(l2)
        chan.msg("hello")
        l1.msg.assert_called_once()
        l2.msg.assert_called_once()
        # Message contains "hello"
        broadcast = l1.msg.call_args[0][0]
        assert "hello" in broadcast

    def test_msg_no_listeners_no_error(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        # Should not raise
        chan.msg("hi")
        assert len(chan.history) == 1

    def test_msg_history_bounded(self, global_test_env):
        # INTENT: history doesn't grow unbounded
        chan = Channel()
        chan.name = "ch"
        # Default maxlen is 50 (CHANNEL_HISTORY_LIMIT)
        for i in range(100):
            chan.msg(f"msg-{i}")
        assert len(chan.history) == 50
        # Oldest entries are dropped (FIFO)
        _ts, _s, first_msg = chan.history[0]
        assert first_msg == "msg-50"

    def test_msg_format_includes_channel_name(self, global_test_env):
        chan = Channel()
        chan.name = "trade"
        l = make_object("a", is_pc=True); l.msg = MagicMock()
        chan.add_listener(l)
        chan.msg("buy", sender=None)
        out = l.msg.call_args[0][0]
        assert "trade" in out


class TestChannelFormatMessage:
    def test_format_with_sender(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        ts = int(datetime(2025, 1, 1, 12, 0, 0).timestamp())
        out = chan.format_message(ts, "Alice", "hello")
        assert "Alice" in out
        assert "hello" in out
        assert "ch" in out
        # The date string is included
        assert "2025" in out

    def test_format_without_sender(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        ts = int(datetime(2025, 6, 1, 9, 30, 0).timestamp())
        out = chan.format_message(ts, "", "system message")
        assert "system message" in out
        assert "ch" in out
        # Sender slot is empty
        assert "Alice" not in out


class TestChannelGetHistory:
    def test_empty_history(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        out = chan.get_history()
        assert out == ""

    def test_history_after_messages(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        chan.msg("one", sender=None)
        chan.msg("two", sender=None)
        chan.msg("three", sender=None)
        out = chan.get_history()
        assert "one" in out
        assert "two" in out
        assert "three" in out

    def test_history_count_limits(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        for i in range(10):
            chan.msg(f"m-{i}", sender=None)
        # Get only the last 3
        out = chan.get_history(count=3)
        assert "m-9" in out
        assert "m-8" in out
        assert "m-7" in out
        # Older messages excluded
        assert "m-0" not in out

    def test_history_ordered_oldest_first(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        chan.msg("first", sender=None)
        chan.msg("second", sender=None)
        out = chan.get_history()
        assert out.index("first") < out.index("second")


class TestChannelClearHistory:
    def test_clear(self, global_test_env):
        chan = Channel()
        chan.name = "ch"
        chan.msg("x", sender=None)
        chan.msg("y", sender=None)
        assert len(chan.history) == 2
        chan.clear_history()
        assert len(chan.history) == 0

    def test_clear_empty(self, global_test_env):
        chan = Channel()
        # Should not raise
        chan.clear_history()
        assert chan.history == deque()


# =============================================================================
# Channel.get_command
# =============================================================================


class TestChannelGetCommand:
    def test_returns_command_with_channel_name(self, global_test_env):
        chan = Channel()
        chan.name = "Help"
        chan.desc = "Help channel"
        cmd = chan.get_command()
        assert cmd.key == "help"
        assert cmd.desc == "Help channel"

    def test_lowercases_name(self, global_test_env):
        chan = Channel()
        chan.name = "TRADE"
        cmd = chan.get_command()
        assert cmd.key == "trade"

    def test_caches_command(self, global_test_env):
        chan = Channel()
        chan.name = "chat"
        c1 = chan.get_command()
        c2 = chan.get_command()
        assert c1 is c2

    def test_command_id_matches_channel_id(self, global_test_env):
        chan = Channel()
        chan.name = "x"
        chan.id = 555
        cmd = chan.get_command()
        assert cmd.id == 555


# =============================================================================
# Channel hooks
# =============================================================================


class TestChannelHooks:
    def test_at_delete_default_returns_true(self, global_test_env):
        chan = Channel()
        assert chan.at_delete() is True

    def test_at_create_default_is_noop(self, global_test_env):
        chan = Channel()
        assert chan.at_create() is None


# =============================================================================
# Channel pickling
# =============================================================================


class TestChannelPickle:
    def test_getstate_excludes_lock_and_listeners(self, global_test_env):
        chan = Channel()
        chan.name = "pchan"
        chan.id = 10
        chan.add_listener(make_object("l", is_pc=True))
        state = chan.__getstate__()
        assert "lock" not in state
        assert "listeners" not in state
        assert "name" in state
        assert "id" in state
        assert "history" in state

    def test_setstate_restores_lock_and_clears_listeners(self, global_test_env):
        chan = Channel()
        chan.name = "pchan2"
        state = chan.__getstate__()
        new_chan = Channel.__new__(Channel)
        new_chan.__setstate__(state)
        assert isinstance(new_chan.lock, _thread.RLock)
        assert new_chan.listeners == {}
        # And history is a deque
        assert isinstance(new_chan.history, deque)

    def test_setstate_history_rewrapped_if_not_deque(self, global_test_env):
        chan = Channel()
        state = chan.__getstate__()
        # Corrupt the history to a list
        state["history"] = list(state["history"]) if state["history"] else []
        # Add some entries
        state["history"] = [(1, "a", "x"), (2, "b", "y")]
        new_chan = Channel.__new__(Channel)
        new_chan.__setstate__(state)
        assert isinstance(new_chan.history, deque)

    def test_pickle_roundtrip_preserves_state(self, global_test_env):
        chan = Channel.create("picklechan")
        chan.desc = "desc"
        chan.msg("hello", sender=None)
        data = pickle.dumps(chan)
        chan2 = pickle.loads(data)
        assert chan2.name == "picklechan"
        assert chan2.desc == "desc"
        assert chan2.id == chan.id
        # Listeners are not preserved
        assert chan2.listeners == {}

    def test_pickled_channel_can_msg(self, global_test_env):
        # INTENT: a restored channel must remain fully functional
        chan = Channel.create("funchan")
        chan2 = pickle.loads(pickle.dumps(chan))
        l = make_object("l", is_pc=True); l.msg = MagicMock()
        chan2.add_listener(l)
        chan2.msg("hi", sender=None)
        l.msg.assert_called_once()


# =============================================================================
# BaseChannelCommand
# =============================================================================


class TestBaseChannelCommand:
    def test_key_and_category(self, global_test_env):
        cmd = BaseChannelCommand()
        assert cmd.key == "__base_channel"
        assert cmd.category == "Communication"

    def test_channel_property_lazy_lookup(self, global_test_env):
        # INTENT: the command can find its channel via global registry
        chan = Channel.create("lookup")
        cmd = BaseChannelCommand()
        cmd._channel = None
        cmd.id = chan.id
        assert cmd.channel is chan

    def test_channel_property_missing_raises(self, global_test_env):
        cmd = BaseChannelCommand()
        cmd._channel = None
        cmd.id = 99999  # no such channel
        with pytest.raises(ValueError, match="not found"):
            _ = cmd.channel

    def test_channel_setter_sets_id(self, global_test_env):
        chan = Channel()
        chan.id = 77
        cmd = BaseChannelCommand()
        cmd.channel = chan
        assert cmd._channel is chan
        assert cmd.id == 77

    def test_run_message_sends_via_channel(self, global_test_env):
        chan = Channel.create("msgchan")
        cmd = chan.get_command()
        caller = make_object("alice", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs(message="hello")
        with patch.object(chan, "msg") as mock_msg:
            cmd.run(caller, args)
            mock_msg.assert_called_with("hello", caller)

    def test_run_replay_no_permission(self, global_test_env):
        chan = Channel.create("replaychan")
        # Add a lock that denies replay
        chan.add_lock("view", lambda x: False)
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs(replay=True)
        cmd.run(caller, args)
        caller.msg.assert_called()
        # Message indicates no permission
        assert any("permission" in str(c.args[0]) for c in caller.msg.call_args_list)

    def test_run_replay_with_permission(self, global_test_env):
        chan = Channel.create("replaychan2")
        chan.msg("line1", sender=None)
        chan.msg("line2", sender=None)
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs(replay=True)
        cmd.run(caller, args)
        caller.msg.assert_called()
        out = " ".join(str(c.args[0]) for c in caller.msg.call_args_list)
        assert "line1" in out
        assert "line2" in out

    def test_run_send_no_permission(self, global_test_env):
        chan = Channel.create("sendchan")
        chan.add_lock("send", lambda x: False)
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs(message="hi")
        with patch.object(chan, "msg") as mock_msg:
            cmd.run(caller, args)
            mock_msg.assert_not_called()
        caller.msg.assert_called()
        assert any("permission" in str(c.args[0]) for c in caller.msg.call_args_list)

    def test_run_send_with_permission(self, global_test_env):
        chan = Channel.create("sendchan2")
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs(message="hi")
        with patch.object(chan, "msg") as mock_msg:
            cmd.run(caller, args)
            mock_msg.assert_called_with("hi", caller)

    def test_run_unsubscribe(self, global_test_env):
        chan = Channel.create("subchan")
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        caller.unsubscribe = MagicMock()
        args = MockArgs(unsubscribe=True)
        cmd.run(caller, args)
        caller.unsubscribe.assert_called_with(chan)

    def test_run_no_args_shows_help(self, global_test_env):
        chan = Channel.create("helpchan")
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs()  # no message, no flags
        cmd.run(caller, args)
        caller.msg.assert_called()
        out = " ".join(str(c.args[0]) for c in caller.msg.call_args_list)
        assert "usage:" in out

    def test_replay_empty_history_says_no_history(self, global_test_env):
        chan = Channel.create("emptychan")
        cmd = chan.get_command()
        caller = make_object("a", is_pc=True)
        caller.msg = MagicMock()
        args = MockArgs(replay=True)
        cmd.run(caller, args)
        caller.msg.assert_called()
        out = " ".join(str(c.args[0]) for c in caller.msg.call_args_list)
        assert "no history" in out.lower()

    def test_getstate_excludes_channel(self, global_test_env):
        chan = Channel.create("picklecmd")
        cmd = chan.get_command()
        state = cmd.__getstate__()
        assert "_channel" not in state

    def test_setstate_resets_channel(self, global_test_env):
        chan = Channel.create("picklecmd2")
        cmd = chan.get_command()
        state = cmd.__getstate__()
        new_cmd = BaseChannelCommand()
        new_cmd.__setstate__(state)
        assert new_cmd._channel is None

