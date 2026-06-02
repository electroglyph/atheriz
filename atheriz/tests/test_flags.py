"""Tests for atheriz.objects.base_flags — Flag mixin and tag management.

These tests focus on intent: that flags default safely, that tag operations
are set-semantics (no duplicates, missing is silent), and that the lock is
used to protect concurrent access.
"""
from __future__ import annotations

import threading

import pytest

from atheriz.objects.base_flags import Flags
from atheriz.utils import ensure_thread_safe


class _FlagsHolder(Flags):
    """Minimal subclass to instantiate Flags without inheriting Object."""
    pass


@pytest.fixture
def flags_obj():
    # The Flags mixin requires a `lock` attribute (for tag operations).
    # _FlagsHolder inherits from Flags, but Flags.__init__ calls super().__init__,
    # which for a plain class falls through to object.__init__. The `lock`
    # attribute is set externally.
    obj = _FlagsHolder()
    import _thread
    obj.lock = _thread.RLock()
    return obj


class TestFlagsConstructor:
    def test_all_boolean_flags_default_false(self, flags_obj):
        # INTENT: a fresh object has all type-flags false until subclassed
        assert flags_obj.is_pc is False
        assert flags_obj.is_npc is False
        assert flags_obj.is_item is False
        assert flags_obj.is_mapable is False
        assert flags_obj.is_container is False
        assert flags_obj.is_script is False
        assert flags_obj.is_account is False
        assert flags_obj.is_channel is False
        assert flags_obj.is_node is False
        assert flags_obj.is_deleted is False
        assert flags_obj.is_connected is False
        assert flags_obj.is_temporary is False
        assert flags_obj.can_hear is False

    def test_is_modified_default_true(self, flags_obj):
        # INTENT: a fresh object is "dirty" (unsaved) by default — this
        # ensures the first autosave cycle picks it up
        assert flags_obj.is_modified is True

    def test_tags_default_empty_set(self, flags_obj):
        assert flags_obj.tags == set()
        assert isinstance(flags_obj.tags, set)

    def test_is_tickable_uses_underscore_attr(self, flags_obj):
        # The public name is a property that reads from the underscore
        # attribute (probably so subclasses can't accidentally set the
        # public name and have it diverge)
        assert flags_obj.is_tickable is False
        flags_obj._is_tickable = True
        assert flags_obj.is_tickable is True

    def test_is_tickable_is_property(self):
        # INTENT: is_tickable is read-only via property
        assert isinstance(Flags.is_tickable, property)


class TestFlagsAddTag:
    def test_add_string_tag(self, flags_obj):
        flags_obj.add_tag("combat")
        assert "combat" in flags_obj.tags

    def test_add_list_of_tags(self, flags_obj):
        flags_obj.add_tag(["a", "b", "c"])
        assert flags_obj.tags == {"a", "b", "c"}

    def test_add_set_of_tags(self, flags_obj):
        flags_obj.add_tag({"x", "y"})
        assert flags_obj.tags == {"x", "y"}

    def test_add_idempotent(self, flags_obj):
        # INTENT: set semantics — no duplicates
        flags_obj.add_tag("foo")
        flags_obj.add_tag("foo")
        assert flags_obj.tags == {"foo"}

    def test_add_sets_is_modified(self, flags_obj):
        flags_obj.is_modified = False
        flags_obj.add_tag("trigger")
        assert flags_obj.is_modified is True

    def test_add_empty_string(self, flags_obj):
        # Even empty strings are added (no validation)
        flags_obj.add_tag("")
        assert "" in flags_obj.tags

    def test_add_overlapping_list_and_string(self, flags_obj):
        flags_obj.add_tag("a")
        flags_obj.add_tag(["a", "b"])
        assert flags_obj.tags == {"a", "b"}

    def test_add_uses_lock(self, monkeypatch, flags_obj):
        # INTENT: tag add is protected by the lock
        import atheriz.objects.base_flags as bf
        calls = []
        # Spy on the lock context manager
        real_lock = flags_obj.lock

        class SpyLock:
            def __enter__(self):
                calls.append("acquire")
                return real_lock.__enter__()
            def __exit__(self, *args):
                return real_lock.__exit__(*args)

        flags_obj.lock = SpyLock()
        flags_obj.add_tag("x")
        assert "acquire" in calls


class TestFlagsRemoveTag:
    def test_remove_existing_tag(self, flags_obj):
        flags_obj.add_tag("present")
        flags_obj.remove_tag("present")
        assert "present" not in flags_obj.tags

    def test_remove_missing_tag_silent(self, flags_obj):
        # INTENT: remove_tag should not raise for missing tags
        flags_obj.remove_tag("never-added")
        assert flags_obj.tags == set()

    def test_remove_string(self, flags_obj):
        flags_obj.add_tag("a")
        flags_obj.add_tag("b")
        flags_obj.remove_tag("a")
        assert flags_obj.tags == {"b"}

    def test_remove_list_of_tags(self, flags_obj):
        flags_obj.add_tag(["a", "b", "c", "d"])
        flags_obj.remove_tag(["a", "c"])
        assert flags_obj.tags == {"b", "d"}

    def test_remove_set_of_tags(self, flags_obj):
        flags_obj.add_tag({"a", "b", "c"})
        flags_obj.remove_tag({"a", "b"})
        assert flags_obj.tags == {"c"}

    def test_remove_missing_in_list(self, flags_obj):
        # INTENT: missing tags in the list are silently ignored
        flags_obj.add_tag("a")
        flags_obj.remove_tag(["a", "missing"])
        assert flags_obj.tags == set()

    def test_remove_sets_is_modified(self, flags_obj):
        flags_obj.add_tag("x")
        flags_obj.is_modified = False
        flags_obj.remove_tag("x")
        assert flags_obj.is_modified is True

    def test_remove_empty_set(self, flags_obj):
        flags_obj.add_tag("a")
        flags_obj.remove_tag(set())  # no-op
        assert flags_obj.tags == {"a"}


class TestFlagsHasTag:
    def test_single_tag_present(self, flags_obj):
        flags_obj.add_tag("a")
        assert flags_obj.has_tag("a") is True

    def test_single_tag_absent(self, flags_obj):
        assert flags_obj.has_tag("missing") is False

    def test_list_any_match(self, flags_obj):
        # INTENT: default behavior is ANY match
        flags_obj.add_tag("a")
        flags_obj.add_tag("b")
        # Any of a, c, d matches because 'a' is present
        assert flags_obj.has_tag(["a", "c", "d"]) is True
        # None of x, y, z matches
        assert flags_obj.has_tag(["x", "y", "z"]) is False

    def test_list_all_match(self, flags_obj):
        # INTENT: with all=True, requires every tag
        flags_obj.add_tag("a")
        flags_obj.add_tag("b")
        assert flags_obj.has_tag(["a", "b"], all=True) is True
        # Missing c makes this fail
        assert flags_obj.has_tag(["a", "c"], all=True) is False

    def test_set_with_all(self, flags_obj):
        flags_obj.add_tag({"a", "b", "c"})
        assert flags_obj.has_tag({"a", "b"}, all=True) is True
        assert flags_obj.has_tag({"a", "z"}, all=True) is False

    def test_empty_tag_list_any(self, flags_obj):
        # No tags requested, intersection is empty, returns False
        assert flags_obj.has_tag([]) is False

    def test_empty_tag_list_all(self, flags_obj):
        # All of nothing is True (vacuously true)
        assert flags_obj.has_tag([], all=True) is True

    def test_has_tag_returns_bool(self, flags_obj):
        # The implementation uses bool() coercion to ensure the return is bool
        result = flags_obj.has_tag("a")
        assert isinstance(result, bool)

    def test_has_tag_set_with_any(self, flags_obj):
        flags_obj.add_tag("a")
        assert flags_obj.has_tag({"a", "b"}) is True


class TestFlagsThreadSafety:
    def test_concurrent_add_tags(self, flags_obj):
        # INTENT: the lock prevents races when many threads add tags
        # concurrently
        errors = []

        def worker(i):
            try:
                flags_obj.add_tag(f"t{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        # All 50 unique tags present
        assert len(flags_obj.tags) == 50

    def test_concurrent_add_and_remove(self, flags_obj):
        # INTENT: simultaneous add and remove operations don't corrupt the set
        flags_obj.add_tag(["a", "b", "c", "d", "e"])
        errors = []

        def adder():
            try:
                for i in range(20):
                    flags_obj.add_tag(f"x{i}")
            except Exception as e:
                errors.append(e)

        def remover():
            try:
                for _ in range(20):
                    flags_obj.remove_tag(["a", "b", "c"])
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=adder)
        t2 = threading.Thread(target=remover)
        t1.start(); t2.start()
        t1.join(); t2.join()
        assert errors == []


class TestFlagsIntegration:
    def test_add_remove_cycle(self, flags_obj):
        flags_obj.add_tag("temp")
        assert flags_obj.has_tag("temp")
        flags_obj.remove_tag("temp")
        assert not flags_obj.has_tag("temp")

    def test_re_add_after_remove(self, flags_obj):
        flags_obj.add_tag("x")
        flags_obj.remove_tag("x")
        flags_obj.add_tag("x")
        assert flags_obj.has_tag("x")

    def test_modify_flag_works(self, flags_obj):
        # INTENT: flags are mutable booleans — subclasses set them in __init__
        flags_obj.is_pc = True
        assert flags_obj.is_pc is True
        flags_obj.is_pc = False
        assert flags_obj.is_pc is False

    def test_subclass_can_initialize(self):
        # INTENT: subclasses set is_* flags to identify their type
        class MyChar(Flags):
            def __init__(self):
                # Bypass the lock requirement for the test
                object.__setattr__(self, "lock", __import__("_thread").RLock())
                super().__init__()
                self.is_pc = True
        c = MyChar()
        assert c.is_pc is True
        assert c.is_npc is False
        assert c.is_modified is True
