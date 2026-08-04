"""Issue tests: `puppet` allowed a builder to impersonate other players'
offline characters and overwrote their `privilege_level`/`is_pc` — a persisted,
protected field — so a mid-puppet autosave or a crash could permanently
re-privilege an arbitrary character.

Fix: a `puppet` access lock gates ownership (NPCs, the caller's own characters,
superusers), and the mutation is made transient via `_puppet_restore`, which
`__getstate__` persists instead of the mutated values.
"""
from __future__ import annotations

import dill

import pytest
from unittest.mock import MagicMock

from atheriz import settings
from atheriz.commands.loggedin.puppet import PuppetCommand
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.objects.session import Session


@pytest.fixture(autouse=True)
def _no_autosave(monkeypatch):
    monkeypatch.setattr(settings, "AUTOSAVE_PLAYERS_ON_DISCONNECT", False)


def _args(target):
    class A:
        pass

    a = A()
    a.target = f"#{target.id}"
    return a


def _builder(name: str):
    """A real builder PC with a session wired to its own account."""
    caller = Object.create(None, name, is_pc=True)
    caller.privilege_level = settings.Privilege.Builder
    account = Account.create(f"{name}_acct", "pw1")
    account.characters = [caller.id]
    session = Session(account=account, connection=MagicMock())
    session.puppet = caller
    caller.session = session
    return caller, session


class TestPuppetGate:
    def test_builder_cannot_puppet_other_players_character(self, global_test_env, fixed_salt):
        """INTENT: a builder must not be able to puppet a PC owned by a
        different account. The current implementation has no ownership check."""
        victim = Object.create(None, "victim", is_pc=True)
        victim.privilege_level = settings.Privilege.Player
        owner = Account.create("owner", "pw1")
        owner.characters = [victim.id]

        caller, session = _builder("builder")

        PuppetCommand().run(caller, _args(victim))

        text = " ".join(str(c.args[0]) for c in session.connection.msg.call_args_list)
        assert "cannot puppet" in text
        assert victim.is_pc is True
        assert victim.privilege_level == settings.Privilege.Player
        assert not hasattr(victim, "_puppet_restore")
        assert session.puppet is caller
        assert session.puppet_stack == []

    def test_builder_can_puppet_own_character(self, global_test_env, fixed_salt):
        caller, session = _builder("builder")
        alt = Object.create(None, "alt", is_pc=True)
        alt.privilege_level = settings.Privilege.Player
        session.account.characters.append(alt.id)

        PuppetCommand().run(caller, _args(alt))

        assert alt.is_pc is True
        assert alt.privilege_level == settings.Privilege.Builder
        assert session.puppet is alt

    def test_builder_can_puppet_npc(self, global_test_env, fixed_salt):
        npc = Object.create(None, "goblin", is_npc=True)

        caller, session = _builder("builder")

        PuppetCommand().run(caller, _args(npc))

        assert npc.is_pc is True
        assert npc.privilege_level == settings.Privilege.Builder
        assert session.puppet is npc

    def test_superuser_can_puppet_any_character(self, global_test_env, fixed_salt):
        victim = Object.create(None, "victim", is_pc=True)
        victim.privilege_level = settings.Privilege.Player
        owner = Account.create("owner", "pw1")
        owner.characters = [victim.id]

        admin, session = _builder("admin")
        admin.privilege_level = settings.Privilege.Admin

        PuppetCommand().run(admin, _args(victim))

        assert victim.is_pc is True
        assert victim.privilege_level == settings.Privilege.Admin
        assert session.puppet is victim


class TestPuppetPersistence:
    def test_puppeted_state_never_serialized(self, global_test_env, fixed_salt):
        """INTENT: while an object is puppeted, the persisted copy must carry
        the ORIGINAL is_pc/privilege_level, never the puppeter's. The old code
        serialized the mutated values, so an autosave or crash permanently
        corrupted the target."""
        npc = Object.create(None, "goblin", is_npc=True)
        caller, session = _builder("builder")

        PuppetCommand().run(caller, _args(npc))

        assert npc.is_pc is True
        assert npc.privilege_level == settings.Privilege.Builder

        blob = npc.get_save_ops()[1][1]
        loaded = dill.loads(blob)
        assert loaded.is_pc is False
        assert loaded.privilege_level == settings.Privilege.Guest
        assert not hasattr(loaded, "_puppet_restore")
