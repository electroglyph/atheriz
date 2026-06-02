"""Tests for atheriz.commands.base_cmdset — CmdSet registry and management."""
from __future__ import annotations

import threading
import _thread
from unittest.mock import MagicMock

import pytest

from atheriz.commands.base_cmd import Command
from atheriz.commands.base_cmdset import CmdSet


class FakeCommand(Command):
    """A minimal Command subclass for cmdset testing."""

    def __init__(self, key="fake", aliases=None, tag=""):
        Command.__init__(self)
        self.key = key
        self.aliases = aliases if aliases is not None else []
        self.tag = tag
        self.desc = f"Fake {key}"
        self.category = "Test"


class TestCmdSetInit:
    def test_empty(self, global_test_env):
        cs = CmdSet()
        assert cs.commands == {}
        assert isinstance(cs.lock, _thread.RLock)


class TestCmdSetGetAll:
    def test_empty_returns_empty_list(self, global_test_env):
        cs = CmdSet()
        assert cs.get_all() == []

    def test_returns_list(self, global_test_env):
        cs = CmdSet()
        cs.add(FakeCommand("a"))
        cs.add(FakeCommand("b"))
        result = cs.get_all()
        assert isinstance(result, list)
        assert len(result) == 2

    def test_includes_aliases_as_same_object(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x", "y"])
        cs.add(c)
        result = cs.get_all()
        # The command is added 3 times to the dict (key + 2 aliases) but get_all returns values
        # values() returns one entry per command-instance-key, and aliases map to same instance
        # so the result has 3 references to the same command object
        assert len(result) == 3
        assert all(c is r for r in result)

    def test_unique_instances(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a")
        b = FakeCommand("b")
        cs.add(a)
        cs.add(b)
        result = cs.get_all()
        # No alias collisions
        assert set(id(c) for c in result) == {id(a), id(b)}


class TestCmdSetAdd:
    def test_add_by_key(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a")
        cs.add(c)
        assert cs.commands["a"] is c

    def test_add_with_aliases(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x", "y"])
        cs.add(c)
        assert cs.commands["a"] is c
        assert cs.commands["x"] is c
        assert cs.commands["y"] is c

    def test_add_overwrites_existing_key(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a")
        b = FakeCommand("a")
        cs.add(a)
        cs.add(b)
        assert cs.commands["a"] is b

    def test_add_overwrites_existing_alias(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", aliases=["x"])
        b = FakeCommand("b", aliases=["x"])
        cs.add(a)
        cs.add(b)
        # 'x' now maps to b
        assert cs.commands["x"] is b

    def test_add_with_tag_sets_command_tag(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a")
        assert c.tag == ""
        cs.add(c, tag="mytag")
        assert c.tag == "mytag"

    def test_add_without_tag_does_not_overwrite(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", tag="existing")
        cs.add(c)
        # tag was not passed, so it stays as set on the command
        assert c.tag == "existing"

    def test_add_no_aliases(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=[])
        cs.add(c)
        assert len(cs.commands) == 1
        assert cs.commands["a"] is c

    def test_add_returns_none(self, global_test_env):
        cs = CmdSet()
        assert cs.add(FakeCommand("a")) is None


class TestCmdSetAdds:
    def test_adds_multiple(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a")
        b = FakeCommand("b")
        c = FakeCommand("c")
        cs.adds([a, b, c])
        assert cs.commands["a"] is a
        assert cs.commands["b"] is b
        assert cs.commands["c"] is c

    def test_adds_with_aliases(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", aliases=["x"])
        b = FakeCommand("b", aliases=["y"])
        cs.adds([a, b])
        assert cs.commands["x"] is a
        assert cs.commands["y"] is b

    def test_adds_with_tag_sets_all(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a")
        b = FakeCommand("b")
        cs.adds([a, b], tag="batch")
        assert a.tag == "batch"
        assert b.tag == "batch"

    def test_adds_without_tag_preserves_existing(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", tag="preserved")
        cs.adds([a])
        assert a.tag == "preserved"

    def test_adds_empty_list(self, global_test_env):
        cs = CmdSet()
        cs.adds([])
        assert cs.commands == {}

    def test_adds_overwrites_duplicates(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a")
        b = FakeCommand("a")
        cs.adds([a, b])
        # The last one wins
        assert cs.commands["a"] is b

    def test_adds_overwrites_aliases(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", aliases=["x"])
        b = FakeCommand("b", aliases=["x"])
        cs.adds([a, b])
        assert cs.commands["x"] is b


class TestCmdSetRemove:
    def test_remove_by_key(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a")
        cs.add(c)
        cs.remove(c)
        assert "a" not in cs.commands

    def test_remove_clears_aliases(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x", "y"])
        cs.add(c)
        cs.remove(c)
        assert "a" not in cs.commands
        assert "x" not in cs.commands
        assert "y" not in cs.commands

    def test_remove_unregistered_command(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a")
        # Should not raise even though c was never added
        cs.remove(c)
        assert cs.commands == {}

    def test_remove_does_not_affect_other_commands(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", aliases=["x"])
        b = FakeCommand("b")
        cs.add(a)
        cs.add(b)
        cs.remove(a)
        assert "a" not in cs.commands
        assert "x" not in cs.commands
        assert cs.commands["b"] is b

    def test_remove_returns_none(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a")
        cs.add(c)
        assert cs.remove(c) is None


class TestCmdSetRemoveByTag:
    def test_removes_all_with_tag(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", tag="t1")
        b = FakeCommand("b", tag="t1")
        c = FakeCommand("c", tag="t2")
        cs.adds([a, b, c])
        cs.remove_by_tag("t1")
        assert "a" not in cs.commands
        assert "b" not in cs.commands
        assert cs.commands["c"] is c

    def test_no_matches_no_change(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", tag="t1")
        cs.add(a)
        cs.remove_by_tag("t2")
        assert cs.commands["a"] is a

    def test_empty_cmdset(self, global_test_env):
        cs = CmdSet()
        cs.remove_by_tag("anything")
        assert cs.commands == {}

    def test_removes_aliases_too(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", aliases=["x"], tag="t1")
        b = FakeCommand("b", tag="t2")
        cs.adds([a, b])
        cs.remove_by_tag("t1")
        assert "a" not in cs.commands
        assert "x" not in cs.commands
        assert cs.commands["b"] is b


class TestCmdSetGet:
    def test_get_by_key(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a")
        cs.add(c)
        assert cs.get("a") is c

    def test_get_by_alias(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x"])
        cs.add(c)
        assert cs.get("x") is c

    def test_get_missing_returns_none(self, global_test_env):
        cs = CmdSet()
        assert cs.get("nope") is None

    def test_get_after_remove(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x"])
        cs.add(c)
        cs.remove(c)
        assert cs.get("a") is None
        assert cs.get("x") is None


class TestCmdSetGetKeys:
    def test_empty(self, global_test_env):
        cs = CmdSet()
        assert cs.get_keys() == []

    def test_returns_all_keys(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", aliases=["x"])
        b = FakeCommand("b")
        cs.adds([a, b])
        keys = cs.get_keys()
        assert set(keys) == {"a", "x", "b"}

    def test_returns_list(self, global_test_env):
        cs = CmdSet()
        cs.add(FakeCommand("a"))
        assert isinstance(cs.get_keys(), list)


class TestCmdSetState:
    def test_getstate_returns_dict(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x"])
        cs.add(c, tag="t")
        state = cs.__getstate__()
        assert isinstance(state, dict)
        assert "commands" in state
        assert "lock" in state
        assert state["commands"]["a"].key == "a"

    def test_setstate_restores_lock(self, global_test_env):
        cs = CmdSet()
        cs2 = CmdSet()
        cs2.__setstate__(cs.__getstate__())
        # After setstate, lock is a fresh RLock
        assert isinstance(cs2.lock, _thread.RLock)
        # And the lock can be acquired
        with cs2.lock:
            pass

    def test_setstate_restores_commands(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x"])
        cs.add(c, tag="t")
        state = cs.__getstate__()
        cs2 = CmdSet()
        cs2.__setstate__(state)
        assert cs2.commands["a"].key == "a"
        assert cs2.commands["a"].tag == "t"
        assert cs2.commands["a"].aliases == ["x"]
        assert cs2.commands["x"] is cs2.commands["a"]

    def test_pickle_directly_fails_due_to_rlock(self, global_test_env):
        # The current __getstate__ includes the RLock in the state, so pickle cannot
        # serialize CmdSet. This is a known limitation of the implementation.
        import pickle
        cs = CmdSet()
        with pytest.raises(TypeError, match="RLock"):
            pickle.dumps(cs)

    def test_pickle_with_command_added_also_fails(self, global_test_env):
        import pickle
        cs = CmdSet()
        cs.add(FakeCommand("a"))
        with pytest.raises(TypeError, match="RLock"):
            pickle.dumps(cs)


class TestCmdSetThreadSafety:
    def test_add_concurrent(self, global_test_env):
        # Basic sanity check: lock is an RLock and operations can be concurrent
        cs = CmdSet()
        errors = []

        def worker(i):
            try:
                cs.add(FakeCommand(f"c{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(cs.commands) == 10

    def test_get_concurrent(self, global_test_env):
        cs = CmdSet()
        cs.add(FakeCommand("a", aliases=["x"]))
        errors = []

        def worker():
            try:
                assert cs.get("a") is not None
                assert cs.get("x") is not None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


class TestCmdSetIntegration:
    def test_add_remove_cycle(self, global_test_env):
        cs = CmdSet()
        c = FakeCommand("a", aliases=["x"])
        cs.add(c)
        assert cs.get("a") is c
        assert cs.get("x") is c
        cs.remove(c)
        assert cs.get("a") is None
        assert cs.get("x") is None
        # Re-add works
        cs.add(c)
        assert cs.get("a") is c

    def test_multiple_cmdsets_independent(self, global_test_env):
        cs1 = CmdSet()
        cs2 = CmdSet()
        a = FakeCommand("a")
        cs1.add(a)
        assert "a" not in cs2.commands

    def test_add_overwrites_in_separate_adds_calls(self, global_test_env):
        cs = CmdSet()
        a = FakeCommand("a", tag="t1")
        b = FakeCommand("a", tag="t2")
        cs.add(a)
        cs.add(b)
        # b overwrote a
        assert cs.get("a") is b
        # b's tag is t2
        assert b.tag == "t2"
