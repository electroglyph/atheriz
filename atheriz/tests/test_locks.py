"""
Tests for lock functionality in Object class.
"""

import pytest
from unittest.mock import patch
from atheriz.objects.base_obj import Object
from atheriz.globals import objects as obj_singleton
import atheriz.settings as settings


@pytest.fixture(autouse=True)
def cleanup():
    """Reset object singleton state before each test."""
    obj_singleton._ALL_OBJECTS.clear()


class MockObject(Object):
    """Simple test subclass of Object."""

    pass


# --- add_lock tests ---


def test_add_lock_creates_lock_list():
    """Test that add_lock creates a new lock list if none exists."""
    obj = MockObject()
    obj.add_lock("control", lambda x: x.is_builder)

    assert "control" in obj.locks
    assert len(obj.locks["control"]) == 1


def test_add_lock_appends_to_existing():
    """Test that add_lock appends to an existing lock list."""
    obj = MockObject()
    obj.add_lock("control", lambda x: x.is_builder)
    obj.add_lock("control", lambda x: x.is_superuser)

    assert "control" in obj.locks
    assert len(obj.locks["control"]) == 2


def test_add_lock_multiple_names():
    """Test that add_lock can handle multiple lock names."""
    obj = MockObject()
    obj.add_lock("control", lambda x: True)
    obj.add_lock("view", lambda x: True)
    obj.add_lock("edit", lambda x: True)

    assert "control" in obj.locks
    assert "view" in obj.locks
    assert "edit" in obj.locks


# --- clear_locks_by_name tests ---


def test_clear_locks_by_name_removes_lock():
    """Test that clear_locks_by_name removes the specified lock."""
    obj = MockObject()
    obj.add_lock("control", lambda x: True)
    obj.add_lock("view", lambda x: True)

    obj.clear_locks_by_name("control")

    assert "control" not in obj.locks
    assert "view" in obj.locks


def test_clear_locks_by_name_nonexistent():
    """Test that clear_locks_by_name handles nonexistent locks gracefully."""
    obj = MockObject()
    obj.add_lock("control", lambda x: True)

    # Should not raise
    obj.clear_locks_by_name("nonexistent")

    assert "control" in obj.locks


def test_clear_locks_by_name_empty_locks():
    """Test that clear_locks_by_name works on empty locks dict."""
    obj = MockObject()

    # Should not raise
    obj.clear_locks_by_name("anything")

    assert len(obj.locks) == 0


# --- access tests (shared logic) ---


def test_access_superuser_bypasses_locks():
    """Test that superusers bypass all lock checks."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 4  # superuser level
    accessor.quelled = False

    # Add a lock that always fails
    obj.add_lock("control", lambda x: False)

    # Superuser should still pass
    assert obj.access(accessor, "control") is True


def test_access_passes_when_no_locks():
    """Test that access passes when no locks exist for the name."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    assert obj.access(accessor, "nonexistent") is True


def test_access_passes_when_all_locks_pass():
    """Test that access passes when all locks return True."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 3  # builder
    accessor.quelled = False

    obj.add_lock("control", lambda x: x.is_builder)
    obj.add_lock("control", lambda x: True)

    assert obj.access(accessor, "control") is True


def test_access_fails_when_any_lock_fails():
    """Test that access fails if any lock returns False."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1  # not a builder
    accessor.quelled = False

    obj.add_lock("control", lambda x: True)
    obj.add_lock("control", lambda x: x.is_builder)  # This will fail

    assert obj.access(accessor, "control") is False


def test_access_with_single_failing_lock():
    """Test access with a single lock that fails."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    obj.add_lock("view", lambda x: False)

    assert obj.access(accessor, "view") is False


def test_access_with_single_passing_lock():
    """Test access with a single lock that passes."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    obj.add_lock("view", lambda x: True)

    assert obj.access(accessor, "view") is True


def test_access_checks_correct_lock_name():
    """Test that access only checks locks for the specified name."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    obj.add_lock("control", lambda x: False)  # Would fail
    obj.add_lock("view", lambda x: True)  # Would pass

    assert obj.access(accessor, "view") is True
    assert obj.access(accessor, "control") is False


# --- SLOW_LOCKS setting tests ---


def test_slow_locks_enabled():
    """Test that Object uses _safe_access when SLOW_LOCKS is True."""
    with patch.object(settings, "SLOW_LOCKS", True):
        obj = MockObject()
        assert obj.access == obj._safe_access


def test_slow_locks_disabled():
    """Test that Object uses _fast_access when SLOW_LOCKS is False."""
    with patch.object(settings, "SLOW_LOCKS", False):
        obj = MockObject()
        assert obj.access == obj._fast_access


def test_safe_access_behavior():
    """Test _safe_access method directly."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    obj.add_lock("test", lambda x: True)

    assert obj._safe_access(accessor, "test") is True

    obj.add_lock("test", lambda x: False)

    assert obj._safe_access(accessor, "test") is False


def test_fast_access_behavior():
    """Test _fast_access method directly."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    obj.add_lock("test", lambda x: True)

    assert obj._fast_access(accessor, "test") is True

    obj.add_lock("test", lambda x: False)

    assert obj._fast_access(accessor, "test") is False


def test_safe_and_fast_access_have_same_behavior():
    """Test that _safe_access and _fast_access produce identical results."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 1
    accessor.quelled = False

    # No locks
    assert obj._safe_access(accessor, "test") == obj._fast_access(accessor, "test")

    # Passing lock
    obj.add_lock("test", lambda x: True)
    assert obj._safe_access(accessor, "test") == obj._fast_access(accessor, "test")

    # Failing lock
    obj.add_lock("test", lambda x: False)
    assert obj._safe_access(accessor, "test") == obj._fast_access(accessor, "test")

    # Superuser
    accessor.privilege_level = 4
    assert obj._safe_access(accessor, "test") == obj._fast_access(accessor, "test")


def test_quelled_superuser():
    """Test that a quelled superuser is checked against locks."""
    obj = MockObject()
    accessor = MockObject()
    accessor.privilege_level = 4  # superuser
    accessor.quelled = True  # but quelled

    obj.add_lock("control", lambda x: x.is_superuser)
    assert obj.access(accessor, "control") is False
