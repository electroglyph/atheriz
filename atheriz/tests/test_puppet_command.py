from __future__ import annotations

import dill

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
        self.is_npc = False
        self.is_connected = False
        self.seconds_played = 0.0
        self.locks = {}
        self.msgs = []
        self.puppet_calls = []
        self.unpuppet_calls = []
        self.disconnect_calls = 0
        self.post_puppet_calls = 0
        # snapshots of state at the moment each hook fired (ordering assertions)
        self.puppet_session_at_call = []
        self.unpuppet_is_pc_at_call = []

    @property
    def is_superuser(self):
        return self.privilege_level >= settings.Privilege.Admin

    @property
    def is_builder(self):
        return self.privilege_level >= settings.Privilege.Builder

    def add_lock(self, lock_name, callable_):
        self.locks.setdefault(lock_name, []).append(callable_)

    def access(self, accessing_obj, name):
        if getattr(accessing_obj, "is_superuser", False):
            return True
        return all(lock(accessing_obj) for lock in self.locks.get(name, []))

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


def _session_with(caller):
    session = Session()
    caller.session = session
    session.puppet = caller
    return session


def _restore(target):
    return getattr(target, "_puppet_restore", None)


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
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
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
        session = _session_with(caller := FakeObj("admin", privilege_level=settings.Privilege.Admin))
        target = FakeObj("goblin")
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.privilege_level == settings.Privilege.Admin

    def test_at_puppet_fires_after_session_wiring(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        # contract for game-side handler hooks: session is already wired when at_puppet fires
        assert target.puppet_session_at_call[-1] is session

    def test_restore_manifest_records_original_state(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("npc", privilege_level=settings.Privilege.Helper, is_pc=False)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert session.puppet_stack == [(caller, target)]
        assert _restore(target) == {"is_pc": False, "privilege_level": settings.Privilege.Helper}

    def test_restore_manifest_records_pc_target(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("pc-alt", privilege_level=settings.Privilege.Player, is_pc=True)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert _restore(target) == {"is_pc": True, "privilege_level": settings.Privilege.Player}


# ---------------------------------------------------------------------------
# D2. Puppet access gate (target.access(caller, "puppet"))
# ---------------------------------------------------------------------------


class TestPuppetGate:
    def test_denied_target_is_not_puppeted(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        target.add_lock("puppet", lambda c: False)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert any(m and "cannot puppet" in m for m in caller.msgs)
        assert target.is_pc is False
        assert _restore(target) is None
        assert session.puppet_stack == []
        assert session.puppet is caller

    def test_denial_skips_hooks_and_disconnect(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        target.add_lock("puppet", lambda c: False)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.puppet_calls == []
        assert target.post_puppet_calls == 0
        assert caller.disconnect_calls == 0

    def test_owner_lock_allows_puppet(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("alt")
        target.add_lock("puppet", lambda c: c is caller)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.is_pc is True
        assert session.puppet is target

    def test_superuser_bypasses_puppet_lock(self, monkeypatch):
        session = _session_with(caller := FakeObj("admin", privilege_level=settings.Privilege.Admin))
        target = FakeObj("other")
        target.add_lock("puppet", lambda c: False)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.is_pc is True
        assert session.puppet is target

    def test_npc_default_lock_allows_puppet(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin", is_pc=False)
        target.is_npc = True
        target.add_lock("puppet", lambda c: target.is_npc)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        assert target.is_pc is True
        assert session.puppet is target


# ---------------------------------------------------------------------------
# E. Unpuppet behavior
# ---------------------------------------------------------------------------


class TestUnpuppet:
    def test_restores_pc_and_privilege_and_returns_to_previous(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
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
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("npc", privilege_level=settings.Privilege.Helper)
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        # restored to Helper, not Guest
        assert target.privilege_level == settings.Privilege.Helper
        assert target.is_pc is False

    def test_at_unpuppet_fires_before_restore(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        # contract for game-side teardown hooks: target is still a PC when at_unpuppet fires
        assert target.unpuppet_is_pc_at_call[-1] is True

    def test_unpuppet_clears_restore_manifest(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        assert _restore(target) is not None

        UnpuppetCommand().run(target, None)

        assert _restore(target) is None

    def test_empty_stack_messages_and_no_mutation(self):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))

        UnpuppetCommand().run(caller, None)

        assert any(m and "not puppeting" in m for m in caller.msgs)
        assert session.puppet_stack == []
        assert session.puppet is caller


# ---------------------------------------------------------------------------
# F. Chain semantics (re-puppet the last thing — LIFO)
# ---------------------------------------------------------------------------


class TestChain:
    def test_lifo_unwind(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        a = FakeObj("a")
        b = FakeObj("b")
        registry = {a.id: a, b.id: b}
        monkeypatch.setattr(puppet_mod, "get", lambda ids: [registry[ids]] if ids in registry else [])

        # caller -> a -> b
        PuppetCommand().run(caller, _args(f"#{a.id}"))
        PuppetCommand().run(a, _args(f"#{b.id}"))
        assert session.puppet is b
        assert a.is_pc is True and a.privilege_level == settings.Privilege.Builder
        assert b.is_pc is True and b.privilege_level == settings.Privilege.Builder
        assert _restore(a) is not None and _restore(b) is not None

        # unpuppet b -> back to a (a still puppeted)
        UnpuppetCommand().run(b, None)
        assert session.puppet is a
        assert b.is_pc is False and b.privilege_level == settings.Privilege.Guest
        assert a.is_pc is True and a.privilege_level == settings.Privilege.Builder
        assert _restore(b) is None and _restore(a) is not None

        # unpuppet a -> back to caller
        UnpuppetCommand().run(a, None)
        assert session.puppet is caller
        assert a.is_pc is False and a.privilege_level == settings.Privilege.Guest
        assert _restore(a) is None

    def test_repuppet_same_target_after_unpuppet(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        UnpuppetCommand().run(target, None)

        # state is clean — puppeting the same target again works
        assert session.puppet_stack == []
        assert _restore(target) is None
        PuppetCommand().run(caller, _args(f"#{target.id}"))
        assert target.is_pc is True
        assert session.puppet is target
        assert len(session.puppet_stack) == 1
        assert _restore(target) is not None


# ---------------------------------------------------------------------------
# G. Guards
# ---------------------------------------------------------------------------


class TestGuards:
    def test_cannot_puppet_self(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        _puppet(caller, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{caller.id}"))

        assert any(m and "already puppeting yourself" in m for m in caller.msgs)
        assert session.puppet_stack == []

    def test_cannot_puppet_node(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        node = FakeObj("room")
        node.is_node = True
        _puppet(node, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{node.id}"))

        assert any(m and "cannot puppet" in m for m in caller.msgs)
        assert node.is_pc is False

    def test_cannot_puppet_account_or_channel(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))

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
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        other = Session()
        target = FakeObj("goblin")
        target.session = other  # puppeted by a different session
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
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        target = FakeObj("goblin")
        _puppet(target, monkeypatch)

        PuppetCommand().run(caller, _args(f"#{target.id}"))
        assert target.is_pc is True

        # session drops without an explicit unpuppet
        session.at_disconnect()

        assert target.is_pc is False
        assert target.privilege_level == settings.Privilege.Guest
        assert session.puppet_stack == []
        assert _restore(target) is None

    def test_chain_disconnect_restores_all_targets(self, monkeypatch):
        session = _session_with(caller := FakeObj("builder", privilege_level=settings.Privilege.Builder))
        a = FakeObj("a")
        b = FakeObj("b")
        registry = {a.id: a, b.id: b}
        monkeypatch.setattr(puppet_mod, "get", lambda ids: [registry[ids]] if ids in registry else [])

        PuppetCommand().run(caller, _args(f"#{a.id}"))
        PuppetCommand().run(a, _args(f"#{b.id}"))

        session.at_disconnect()

        assert a.is_pc is False and a.privilege_level == settings.Privilege.Guest
        assert b.is_pc is False and b.privilege_level == settings.Privilege.Guest
        assert session.puppet_stack == []
        assert _restore(a) is None and _restore(b) is None

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
        assert _restore(target) is not None

        UnpuppetCommand().run(target, None)

        assert target.is_pc is False  # reverted to its original non-PC state
        assert target.privilege_level == settings.Privilege.Guest
        assert target.is_connected is False  # real at_disconnect ran
        assert session.puppet is caller
        assert caller.is_connected is True  # prev re-puppeted via real at_post_puppet
        assert session.puppet_stack == []
        assert _restore(target) is None

    def test_real_object_gate_denies_other_players_pc(self, monkeypatch, global_test_env, fixed_salt):
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)
        from atheriz.objects.base_account import Account

        victim = make_object("victim", is_pc=True, privilege_level=settings.Privilege.Player)
        owner = Account.create("owner", "pw1")
        owner.characters = [victim.id]

        session = Session(connection=MagicMock())
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller

        PuppetCommand().run(caller, _args(f"#{victim.id}"))

        text = " ".join(str(c.args[0]) for c in session.connection.msg.call_args_list)
        assert "cannot puppet" in text
        assert victim.is_pc is True
        assert victim.privilege_level == settings.Privilege.Player
        assert session.puppet_stack == []

    def test_real_object_gate_allows_owned_pc(self, monkeypatch, global_test_env, fixed_salt):
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)
        from atheriz.objects.base_account import Account

        session = Session(connection=MagicMock())
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        account = Account.create("bob", "pw1")
        account.characters = [caller.id]
        session.account = account
        session.puppet = caller
        caller.session = session

        alt = make_object("alt", is_pc=True, privilege_level=settings.Privilege.Player)
        account.characters.append(alt.id)

        PuppetCommand().run(caller, _args(f"#{alt.id}"))

        assert alt.is_pc is True
        assert alt.privilege_level == settings.Privilege.Builder
        assert session.puppet is alt


# ---------------------------------------------------------------------------
# J. Persistence safety — puppeted state never reaches the database
# ---------------------------------------------------------------------------


class TestPersistenceSafety:
    def test_getstate_persists_original_state_while_puppeted(self, monkeypatch, global_test_env):
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)

        session = Session(connection=MagicMock())
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller
        target = make_object("goblin", is_npc=True, privilege_level=settings.Privilege.Guest)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        # in memory it acts as the puppeter...
        assert target.is_pc is True
        assert target.privilege_level == settings.Privilege.Builder

        state = target.__getstate__()
        assert state["is_pc"] is False
        assert state["privilege_level"] == int(settings.Privilege.Guest)
        assert "_puppet_restore" not in state

    def test_puppet_restore_never_serialized(self, monkeypatch, global_test_env):
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)

        session = Session(connection=MagicMock())
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller
        target = make_object("goblin", is_npc=True, privilege_level=settings.Privilege.Guest)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        blob = target.get_save_ops()[1][1]
        loaded = dill.loads(blob)
        assert loaded.is_pc is False
        assert loaded.privilege_level == settings.Privilege.Guest
        assert not hasattr(loaded, "_puppet_restore")

    def test_crash_before_teardown_leaves_disk_clean(self, monkeypatch, global_test_env):
        """Simulate the process dying mid-puppet: the object is serialized with
        `_puppet_restore` still set and is never unpuppeted. The persisted state
        must still be the original."""
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)

        session = Session(connection=MagicMock())
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller
        target = make_object("goblin", is_npc=True, privilege_level=settings.Privilege.Guest)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        # (no unpuppet / no at_disconnect — process "dies" now)
        assert _restore(target) is not None
        blob = target.get_save_ops()[1][1]
        loaded = dill.loads(blob)
        assert loaded.is_pc is False
        assert loaded.privilege_level == settings.Privilege.Guest

    def test_persisted_restore_survives_full_save_load_cycle(self, monkeypatch, global_test_env):
        monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)

        session = Session(connection=MagicMock())
        caller = make_object("builder", is_pc=True, privilege_level=settings.Privilege.Builder)
        caller.session = session
        session.puppet = caller
        target = make_object("goblin", is_npc=True, privilege_level=settings.Privilege.Guest)

        PuppetCommand().run(caller, _args(f"#{target.id}"))

        save_ops = target.get_save_ops()[1][1]

        # unpuppet gracefully, then re-load what WOULD have been saved mid-puppet
        UnpuppetCommand().run(target, None)
        loaded = dill.loads(save_ops)
        assert loaded.is_pc is False
        assert loaded.privilege_level == settings.Privilege.Guest
