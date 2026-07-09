from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from atheriz import settings
from atheriz.commands.loggedin import puppet as puppet_mod
from atheriz.commands.loggedin.puppet import PuppetCommand, UnpuppetCommand, _find_target
from atheriz.objects.session import Session
from atheriz.tests.fakes import make_object

# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


# ponytail: lightweight stand-in covering exactly the surface the puppet command
# touches. Isolates the command's stack/restore logic from framework heavy hooks
# (at_post_puppet/at_disconnect are stubbed). Records call-time state so hook
# ordering can be asserted.
class FakeObj:
    _next_id = 0

    def __init__(self, name="obj", privilege_level=settings.Privilege.Guest, is_pc=False):
        self.name = name
        self.id = FakeObj._next_id
        FakeObj._next_id += 1
        self.privilege_level = privilege_level
        self.is_pc = is_pc
        self.session = None
        self.is_deleted = False
        self.is_account = False
        self.is_channel = False
        self.is_node = False
        self.is_connected = False
        self.seconds_played = 0.0
        self.msgs = []
        self.puppet_calls = []
        self.unpuppet_calls = []
        self.disconnect_calls = 0
        self.post_puppet_calls = 0
        # snapshots of state at the moment each hook fired (ordering assertions)
        self.puppet_session_at_call = []
        self.unpuppet_is_pc_at_call = []

    @property
    def is_builder(self):
        return self.privilege_level >= settings.Privilege.Builder

    def msg(self, text=None, **kwargs):
        self.msgs.append(text)

    def at_disconnect(self):
        self.disconnect_calls += 1
        self.session = None
        self.is_connected = False

    def at_puppet(self, caller=None):
        self.puppet_calls.append(caller)
        self.puppet_session_at_call.append(self.session)

    def at_unpuppet(self, caller=None):
        self.unpuppet_calls.append(caller)
        self.unpuppet_is_pc_at_call.append(self.is_pc)

    def at_post_puppet(self, **kwargs):
        self.post_puppet_calls += 1
        self.is_connected = True


def _args(target):
    class A:
        pass

    a = A()
    a.target = target
    return a


def _puppet(target, monkeypatch):
    """Patch the #id lookup to return `target`, for command-logic tests."""
    monkeypatch.setattr(puppet_mod, "get", lambda ids: [target])


# ---------------------------------------------------------------------------
# A. Command surface
# ---------------------------------------------------------------------------


class TestCommandAttributes:
    def test_puppet_attrs(self):
        cmd = PuppetCommand()
        assert cmd.key == "puppet"
        assert cmd.category == "Building"
        assert cmd.aliases == []
        assert cmd.use_parser is True

    def test_unpuppet_attrs(self):
        cmd = UnpuppetCommand()
        assert cmd.key == "unpuppet"
        assert cmd.category == "Building"
        assert cmd.use_parser is False

    def test_puppet_parser_has_target(self):
        parsed = PuppetCommand().parser.parse_args(["goblin"])
        assert parsed.target == "goblin"


# ---------------------------------------------------------------------------
# B. Access control
# ---------------------------------------------------------------------------


class TestAccess:
    def test_puppet_denied_for_non_builder(self):
        cmd = PuppetCommand()
        assert cmd.access(FakeObj("p", privilege_level=settings.Privilege.Player)) is False

    def test_puppet_granted_for_builder(self):
        cmd = PuppetCommand()
        assert cmd.access(FakeObj("b", privilege_level=settings.Privilege.Builder)) is True

    def test_unpuppet_denied_for_non_builder(self):
        cmd = UnpuppetCommand()
        assert cmd.access(FakeObj("p", privilege_level=settings.Privilege.Player)) is False

    def test_unpuppet_granted_for_builder(self):
        cmd = UnpuppetCommand()
        assert cmd.access(FakeObj("b", privilege_level=settings.Privilege.Builder)) is True


# ---------------------------------------------------------------------------
# C. Target resolution
# ---------------------------------------------------------------------------


# Stand-in holder with a controllable search(), for testing _find_target's
# dispatch (inventory vs room vs #id) without booting real Object machinery.
class _Searchable:
    def __init__(self, results=None):
        self._results = results or []
        self.location = None
        self.name = "searchable"

    def search(self, query):
        return list(self._results)


class TestFindTarget:
    def test_id_lookup_is_global(self, global_test_env):
        goblin = make_object("goblin")
        target, err = _find_target(_Searchable(), f"#{goblin.id}")
        assert err is None
        assert target is goblin

    def test_id_invalid_format(self):
        target, err = _find_target(_Searchable(), "#abc")
        assert target is None
        assert "Invalid ID format" in err

    def test_id_not_found(self):
        target, err = _find_target(_Searchable(), "#999999")
        assert target is None
        assert "No object found" in err

    def test_name_found_in_inventory(self):
        goblin = FakeObj("goblin")
        caller = _Searchable(results=[goblin])
        target, err = _find_target(caller, "goblin")
        assert err is None
        assert target is goblin

    def test_name_falls_back_to_room(self):
        goblin = FakeObj("goblin")
        room = _Searchable(results=[goblin])
        caller = _Searchable(results=[])
        caller.location = room
        target, err = _find_target(caller, "goblin")
        assert err is None
        assert target is goblin

    def test_inventory_takes_precedence_over_room(self):
        inv = FakeObj("inv-goblin")
        room_goblin = FakeObj("room-goblin")
        room = _Searchable(results=[room_goblin])
        caller = _Searchable(results=[inv])
        caller.location = room
        target, err = _find_target(caller, "goblin")
        assert target is inv

    def test_no_match(self):
        caller = _Searchable(results=[])
        target, err = _find_target(caller, "ghost")
        assert target is None
        assert "No match" in err

    def test_multiple_matches_disambiguate(self):
        one = FakeObj("goblin")
        two = FakeObj("goblin")
        caller = _Searchable(results=[one, two])
        target, err = _find_target(caller, "goblin")
        assert target is None
        assert "Multiple matches" in err
        assert "#" in err

    def test_alias_resolves_via_real_search(self, global_test_env):
        # the reported bug: name "A big red button", alias "button"
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord

        room = Node(coord=Coord("TA", 0, 0, 0))
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        caller.location = room
        button = make_object("A big red button", is_item=True, aliases=["button"])
        room._contents.add(button.id)

        target, err = _find_target(caller, "button")

        assert err is None
        assert target is button


# ---------------------------------------------------------------------------
# D. Puppet behavior
# ---------------------------------------------------------------------------


class TestPuppet:
    def test_makes_target_pc_and_raises_privilege(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.is_pc is True
        assert target.privilege_level == settings.Privilege.Builder
        assert session.puppet is target
        assert target.session is session
        assert len(session.puppet_stack) == 1
        assert target.puppet_calls == [caller]
        assert target.post_puppet_calls == 1
        assert caller.disconnect_calls == 1

    def test_admin_privilege_copied(self, monkeypatch):
        session = Session()
        caller = FakeObj("admin", privilege_level=settings.Privilege.Admin)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.privilege_level == settings.Privilege.Admin

    def test_at_puppet_fires_after_session_wiring(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        # contract for game-side handler hooks: session is already wired when at_puppet fires
        assert target.puppet_session_at_call[-1] is session

    def test_stack_records_original_state(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("npc", privilege_level=settings.Privilege.Helper, is_pc=False)
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        prev, t, orig_is_pc, orig_priv = session.puppet_stack[0]
        assert prev is caller
        assert t is target
        assert orig_is_pc is False
        assert orig_priv == settings.Privilege.Helper


# ---------------------------------------------------------------------------
# E. Unpuppet behavior
# ---------------------------------------------------------------------------


class TestUnpuppet:
    def test_restores_pc_and_privilege_and_returns_to_previous(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        assert target.is_pc is False
        assert target.privilege_level == settings.Privilege.Guest
        assert session.puppet is caller
        assert caller.session is session
        assert len(session.puppet_stack) == 0
        assert target.unpuppet_calls == [caller]
        assert target.disconnect_calls == 1
        assert caller.post_puppet_calls == 1  # re-puppeted

    def test_restores_nonzero_original_privilege(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("npc", privilege_level=settings.Privilege.Helper)
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        # restored to Helper, not Guest
        assert target.privilege_level == settings.Privilege.Helper
        assert target.is_pc is False

    def test_at_unpuppet_fires_before_restore(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        # contract for game-side teardown hooks: target is still a PC when at_unpuppet fires
        assert target.unpuppet_is_pc_at_call[-1] is True

    def test_empty_stack_messages_and_no_mutation(self):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller

        UnpuppetCommand().run(caller, None)

        assert any(m and "not puppeting" in m for m in caller.msgs)
        assert session.puppet_stack == []
        assert session.puppet is caller


# ---------------------------------------------------------------------------
# F. Chain semantics (re-puppet the last thing — LIFO)
# ---------------------------------------------------------------------------


class TestChain:
    def test_lifo_unwind(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        a = FakeObj("a")
        b = FakeObj("b")
        caller.session = session
        session.puppet = caller
        registry = {a.id: a, b.id: b}
        monkeypatch.setattr(puppet_mod, "get", lambda ids: [registry[ids]] if ids in registry else [])

        # caller -> a -> b
        PuppetCommand().run(caller, _args(f"#{a.id}"))
        PuppetCommand().run(a, _args(f"#{b.id}"))
        assert session.puppet is b
        assert a.is_pc is True and a.privilege_level == settings.Privilege.Builder
        assert b.is_pc is True and b.privilege_level == settings.Privilege.Builder

        # unpuppet b -> back to a (a still puppeted)
        UnpuppetCommand().run(b, None)
        assert session.puppet is a
        assert b.is_pc is False and b.privilege_level == settings.Privilege.Guest
        assert a.is_pc is True and a.privilege_level == settings.Privilege.Builder

        # unpuppet a -> back to caller
        UnpuppetCommand().run(a, None)
        assert session.puppet is caller
        assert a.is_pc is False and a.privilege_level == settings.Privilege.Guest

    def test_repuppet_same_target_after_unpuppet(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        # state is clean — puppeting the same target again works
        assert session.puppet_stack == []
        PuppetCommand().run(caller, _args(f"#{target.id}"))
        assert target.is_pc is True
        assert session.puppet is target
        assert len(session.puppet_stack) == 1


# ---------------------------------------------------------------------------
# G. Guards
# ---------------------------------------------------------------------------


class TestGuards:
    def test_cannot_puppet_self(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller
        _puppet(caller, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{caller.id}"))

        assert any(m and "already puppeting yourself" in m for m in caller.msgs)
        assert session.puppet_stack == []

    def test_cannot_puppet_node(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        node = FakeObj("room")
        node.is_node = True
        caller.session = session
        session.puppet = caller
        _puppet(node, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{node.id}"))

        assert any(m and "cannot puppet" in m for m in caller.msgs)
        assert node.is_pc is False

    def test_cannot_puppet_account_or_channel(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller

        acc = FakeObj("acc")
        acc.is_account = True
        chan = FakeObj("chan")
        chan.is_channel = True

        for meta in (acc, chan):
            _puppet(meta, monkeypatch)
            caller.msgs.clear()
            PuppetCommand().run(caller, _args(f"#{meta.id}"))
            assert any(m and "cannot puppet" in m for m in caller.msgs), meta.name
            assert meta.is_pc is False

    def test_cannot_puppet_already_puppeted_elsewhere(self, monkeypatch):
        session = Session()
        other = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        target.session = other  # puppeted by a different session
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert any(m and "already being puppeted" in m for m in caller.msgs)
        assert target.is_pc is False
        assert session.puppet is caller  # unchanged

    def test_puppet_without_session_messages(self):
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        caller.session = None

        PuppetCommand().run(caller, _args("#1"))

        assert any(m and "no active session" in m for m in caller.msgs)

    def test_unpuppet_without_session_messages(self):
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        caller.session = None

        UnpuppetCommand().run(caller, None)

        assert any(m and "no active session" in m for m in caller.msgs)


# ---------------------------------------------------------------------------
# H. Disconnect safety / data integrity (Session.at_disconnect unwinds the stack)
# ---------------------------------------------------------------------------


class TestDisconnectUnwind:
    def test_mid_puppet_disconnect_restores_target(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        target = FakeObj("goblin")
        caller.session = session
        session.puppet = caller
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        assert target.is_pc is True

        # session drops without an explicit unpuppet
        session.at_disconnect()

        assert target.is_pc is False
        assert target.privilege_level == settings.Privilege.Guest
        assert session.puppet_stack == []

    def test_chain_disconnect_restores_all_targets(self, monkeypatch):
        session = Session()
        caller = FakeObj("builder", privilege_level=settings.Privilege.Builder)
        a = FakeObj("a")
        b = FakeObj("b")
        caller.session = session
        session.puppet = caller
        registry = {a.id: a, b.id: b}
        monkeypatch.setattr(puppet_mod, "get", lambda ids: [registry[ids]] if ids in registry else [])

        PuppetCommand().run(caller, _args(f"#{a.id}"))
        PuppetCommand().run(a, _args(f"#{b.id}"))

        session.at_disconnect()

        assert a.is_pc is False and a.privilege_level == settings.Privilege.Guest
        assert b.is_pc is False and b.privilege_level == settings.Privilege.Guest
        assert session.puppet_stack == []

    def test_empty_stack_disconnect_is_noop(self):
        session = Session()
        session.at_disconnect()  # must not raise
        assert session.puppet_stack == []


# ---------------------------------------------------------------------------
# I. Integration — real Object + real Session through real at_post_puppet/at_disconnect
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_real_object_round_trip(self, monkeypatch, global_test_env):
        # avoid autosave-on-disconnect side effects muddying the assertions
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)

        session = Session()
        session.connection = MagicMock()
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        target = make_object("goblin", is_npc=True, privilege_level=settings.Privilege.Guest)
        caller.session = session
        session.puppet = caller

        # real registry lookup — target was registered by make_object
        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.is_pc is True
        assert target.privilege_level == settings.Privilege.Builder
        assert target.is_connected is True  # real at_post_puppet ran
        assert session.puppet is target
        assert target.session is session

        UnpuppetCommand().run(target, None)

        assert target.is_pc is False  # reverted to its original non-PC state
        assert target.privilege_level == settings.Privilege.Guest
        assert target.is_connected is False  # real at_disconnect ran
        assert session.puppet is caller
        assert caller.is_connected is True  # prev re-puppeted via real at_post_puppet
        assert session.puppet_stack == []
