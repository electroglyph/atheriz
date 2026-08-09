"""Regression tests for assorted engine behaviors.

Every test here encodes the *intended* behavior; it currently fails against
the buggy code and should pass once the corresponding defect is fixed.

Covered defects (see issues.md):
- ``unfollow`` command never registered on the logged-in cmdset.
- ``NodeArea.remove_linked_area`` recurses forever between linked areas.
- ``copy_word_case`` crashes (IndexError) on a longer mixed-case word.
- unloggedin ``help`` crashes (AttributeError) for parserless commands.
- unloggedin command resolution never checks ``cmd.access()``.
- quoted shlex multi-word arguments keep literal quotes in parser commands.
"""

import types

import pytest

from atheriz import inputfuncs
from atheriz.commands.base_cmd import Command
from atheriz.commands.unloggedin.help import HelpCommand
from atheriz.globals.get import get_loggedin_cmdset, get_node_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import NodeArea
from atheriz.tests.fakes import FakeConnection
from atheriz.utils import copy_word_case


def test_unfollow_command_is_registered(global_test_env):
    """The logged-in cmdset must register ``unfollow``.

    ``UnfollowCommand`` (follow.py) is never added to ``LoggedinCmdSet``,
    so a follower has no way to stop following.
    """
    cmd = get_loggedin_cmdset().get("unfollow")
    assert cmd is not None
    assert cmd.key == "unfollow"


def test_linked_area_removal_terminates(global_test_env):
    """Removing a linked area must terminate and clear both link sets.

    ``A.remove_linked_area("B")`` currently cross-recurses through
    ``B.remove_linked_area("A")`` forever -> RecursionError.
    """
    nh = get_node_handler()
    a = NodeArea("AA")
    b = NodeArea("BB")
    a.grids = {0: object()}
    b.grids = {0: object()}
    nh.add_area(a)
    nh.add_area(b)

    a.add_linked_area("BB")
    assert a.linked_areas == {"BB"}
    assert b.linked_areas == {"AA"}

    a.remove_linked_area("BB")

    assert a.linked_areas == set()
    assert b.linked_areas == set()


def test_copy_word_case_survives_longer_equal_case_word():
    """copy_word_case handles a new_word longer than a mixed-case base word.

    The mixed-case branch indexes ``base_word[ic]`` for every character of
    ``new_word`` and slices ``new_word[maxlen - 1:]``; for a longer input --
    which the docstring explicitly supports -- it raises IndexError.
    """
    result = copy_word_case("CoRr", "abcdefg")
    assert isinstance(result, str)
    assert len(result) == len("abcdefg")


def test_unloggedin_help_parserless_command_no_crash(global_test_env):
    """``help quit``/``help new`` must render help instead of crashing.

    print_help() dereferences ``self.parser`` which is None for
    ``use_parser=False`` commands.
    """
    caller = types.SimpleNamespace(
        session=types.SimpleNamespace(screenreader=False, term_width=80),
    )
    caller.msgs = []
    caller.msg = lambda text, *kwargs: caller.msgs.append(str(text))

    HelpCommand().run(caller, types.SimpleNamespace(command="quit"))

    assert any("quit" in m.lower() for m in caller.msgs)


def test_unloggedin_dispatch_enforces_access(global_test_env, monkeypatch):
    """Unloggedin command resolution must respect cmd.access().

    ``_resolve_unloggedin`` currently never consults ``access()`` (unlike the
    logged-in path), so a restricted command would silently run.
    """

    ran = []

    class RestrictedCommand(Command):
        key = "secretcmd"
        use_parser = False

        def access(self, caller):
            return False

        def run(self, caller, args):
            ran.append(True)

    class FakeCmdSet:
        def get(self, key):
            return RestrictedCommand() if key == "secretcmd" else None

    monkeypatch.setattr(inputfuncs, "get_unloggedin_cmdset", lambda: FakeCmdSet())

    connection = FakeConnection()
    job = inputfuncs._resolve_unloggedin(connection, "secretcmd")
    assert job is None, "an access-denied command must not be dispatched"
    assert not ran


def test_parser_commands_strip_quotes(global_test_env):
    """A quoted multi-word argument must arrive unquoted.

    ``Command.execute`` splits with ``shlex.split(args_string, posix=False)``,
    which keeps the literal quotes, contrary to its docstring and to what
    every quoted search/channel/emote argument needs.
    """

    class TCommand(Command):
        key = "t"

        def setup_parser(self):
            self.parser.add_argument("words", nargs="*")

    cmd = TCommand()
    func, caller, args = cmd.execute(None, '"hello world"', "t")
    assert args.words == ["hello world"]


def test_delete_command_not_found_no_crash(global_test_env):
    """Deleting a name that resolves to nothing reports 'no match'.

    When ``caller.search()`` returns [] and ``caller.location`` is None (or its
    ``view`` access is denied), ``DeleteCommand.run`` falls through with
    ``target = []`` and ``target.access(...)`` raises AttributeError instead of
    telling the caller nothing matched.
    """

    class RecvObject(Object):
        def __init__(self):
            super().__init__()
            self.sent = []

        def at_msg_receive(self, text=None, **kwargs):
            self.sent.append(text)
            return True

    from atheriz.commands.loggedin.delete import DeleteCommand

    caller = RecvObject.create(None, "Builder")
    assert caller.search("nope") == []

    DeleteCommand().run(
        caller, types.SimpleNamespace(target=["nope"], recursive=False)
    )

    assert any("No match" in (m or "") for m in caller.sent)


def test_delete_no_match_when_location_view_denied(global_test_env):
    """Deleting when the caller's location denies view reports 'no match'
    instead of crashing on `[].access(...)`."""
    from atheriz.commands.loggedin.delete import DeleteCommand
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node
    from atheriz.utils import Coord

    class RecvObject(Object):
        def __init__(self):
            super().__init__()
            self.sent = []

        def at_msg_receive(self, text=None, **kwargs):
            self.sent.append(text)
            return True

    caller = RecvObject.create(None, "Builder")
    loc = Node(coord=Coord("a", 0, 0, 0))
    loc.add_lock("view", lambda x: False)
    caller.location = loc

    DeleteCommand().run(
        caller, types.SimpleNamespace(target=["nope"], recursive=False)
    )

    assert any("No match" in (m or "") for m in caller.sent)


def test_group_kick_clears_group_channel(global_test_env):
    """Kicking a player from a group must clear their group_channel.

    ``group kick`` removes the target from the channel's listeners but never
    resets ``target.group_channel``, so the kicked player still sees stale
    group state and 'spells' still route to them.
    """
    from atheriz.commands.loggedin.group import GroupCommand
    from atheriz.objects.base_channel import Channel
    from atheriz.objects.base_obj import Object

    leader = Object.create(None, "Leader")
    victim = Object.create(None, "Victim")
    leader._contents.add(victim.id)

    channel = Channel.create("Leader's group", leader)
    channel.add_listener(leader)
    channel.add_listener(victim)
    leader.group_channel = channel.id
    victim.group_channel = channel.id

    GroupCommand().run(leader, types.SimpleNamespace(args=["kick", "Victim"]))

    assert victim.id not in channel.listeners
    assert victim.group_channel is None, "kicked member must be dropped from the group"


def test_msg_passes_text_to_at_msg_send(global_test_env):
    """Object.msg must forward the message body to at_msg_send hooks.

    ``Object.msg`` calls ``obj.at_msg_send(to_obj=..., msg_type=...)`` but never
    passes the actual text, so send-hooks declared with ``text=`` can never
    observe or censor the message body.
    """

    class Sender(Object):
        def __init__(self):
            super().__init__()
            self.seen = None

        def at_msg_send(self, **kwargs):
            self.seen = kwargs

    sender = Sender.create(None, "S")
    sender.msg("hello there!", from_obj=sender)

    assert sender.seen is not None
    assert sender.seen.get("text") == "hello there!"
    assert sender.seen.get("to_obj") is sender

def test_msg_passes_text_kwarg_to_at_msg_send(global_test_env):
    class Sender(Object):
        def __init__(self):
            super().__init__()
            self.seen = None

        def at_msg_send(self, **kwargs):
            self.seen = kwargs

    sender = Sender.create(None, "S")
    sender.msg(text="via kwarg", from_obj=sender)

    assert sender.seen is not None
    assert sender.seen.get("text") == "via kwarg"

def test_msg_passes_text_to_all_at_msg_send_senders(global_test_env):
    class Sender(Object):
        def __init__(self):
            super().__init__()
            self.seen = None

        def at_msg_send(self, **kwargs):
            self.seen = kwargs

    first = Sender.create(None, "First")
    second = Sender.create(None, "Second")
    first.msg("multi", from_obj=[first, second])

    assert first.seen is not None and first.seen.get("text") == "multi"
    assert second.seen is not None and second.seen.get("text") == "multi"

def test_msg_passes_text_without_clobbering_msg_type_or_kwargs(global_test_env):
    class Sender(Object):
        def __init__(self):
            super().__init__()
            self.seen = None

        def at_msg_send(self, **kwargs):
            self.seen = kwargs

    sender = Sender.create(None, "S")
    sender.msg("typed", msg_type="say", foo=1, from_obj=sender)

    assert sender.seen is not None
    assert sender.seen.get("text") == "typed"
    assert sender.seen.get("msg_type") == "say"
    assert sender.seen.get("foo") == 1

def test_at_msg_send_hook_observes_message_body(global_test_env):
    class _CensorHook:
        is_before = True
        is_after = False
        is_replace = False

        def __init__(self):
            self.text = None
            self.to_obj = None

        def __call__(self, text=None, to_obj=None, **kwargs):
            self.text = text
            self.to_obj = to_obj

    sender = Object.create(None, "S")
    hook = _CensorHook()
    sender.hooks["at_msg_send"] = {hook}

    sender.msg("secret", from_obj=sender)

    assert hook.text == "secret"
    assert hook.to_obj is sender

def test_msg_positional_text_still_reaches_at_msg_receive(global_test_env):
    class Receiver(Object):
        def __init__(self):
            super().__init__()
            self.seen = None

        def at_msg_receive(self, **kwargs):
            self.seen = kwargs
            return True

    receiver = Receiver.create(None, "R")
    sender = Object.create(None, "S")
    receiver.msg("body", msg_type="say", from_obj=sender)

    assert receiver.seen is not None
    assert receiver.seen.get("text") == "body"
    assert receiver.seen.get("msg_type") == "say"

def test_msg_contents_passes_text_to_sender_at_msg_send(global_test_env):
    class Sender(Object):
        def __init__(self):
            super().__init__()
            self.seen = None

        def at_msg_send(self, **kwargs):
            self.seen = kwargs

    sender = Sender.create(None, "S")
    receiver = Object.create(None, "R")
    room = Object.create(None, "Room")
    room._contents.add(receiver.id)

    room.msg_contents("hi", from_obj=sender)

    assert sender.seen is not None
    assert sender.seen.get("text") == "hi"
    assert sender.seen.get("to_obj") is receiver