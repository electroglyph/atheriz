"""Pinned tests for 5.8 — SLOW_LOCKS forced in free-threaded.

INTENT: `SLOW_LOCKS=False` reads `self.locks` without `self.lock`
(`_fast_access`) — torn dict/list in free-threaded (no GIL). `settings.py`
documents this and forces `SLOW_LOCKS=True` when `sys._is_gil_enabled()==False`
(free-threaded without GIL). `Barrier` forces the `add_lock` vs `access` race.
"""
from __future__ import annotations

import sys
import threading
from unittest.mock import patch

import atheriz.settings as settings
from atheriz.objects.base_obj import Object


def test_slow_locks_forced_when_gil_disabled(monkeypatch):
    """When `sys._is_gil_enabled()==False` (free-threaded no GIL), reload of
    `settings` must force `SLOW_LOCKS=True` even if game tried to set False.
    Uses public API `sys._is_gil_enabled` (exists in 3.13t/3.14t) with fallback."""
    import importlib

    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False, raising=False)
    # also ensure if sys.is_gil_enabled exists, it matches
    if hasattr(sys, "is_gil_enabled"):
        monkeypatch.setattr(sys, "is_gil_enabled", lambda: False, raising=False)

    # reload settings to trigger top-level GIL check
    importlib.reload(settings)
    assert settings.SLOW_LOCKS is True, "SLOW_LOCKS not forced in free-threaded"

    # even explicit False via game folder must be overridden on next reload
    # simulate game folder injection `setattr(settings, "SLOW_LOCKS", False)`
    # then re-apply forcing by reloading (or by checking AccessLock)
    settings.SLOW_LOCKS = False
    importlib.reload(settings)
    assert settings.SLOW_LOCKS is True

    # restore GIL enabled for rest of suite
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: True, raising=False)
    importlib.reload(settings)
    # now SLOW_LOCKS should be whatever default (True) — not forced
    # we leave it True for safety; test that _fast_access can be used when explicitly False
    with patch.object(settings, "SLOW_LOCKS", False):
        obj = Object.create(None, "test_gil_safe")
        # In GIL-enabled build with SLOW_LOCKS=False, fast path is allowed
        # (but still documented unsafe for free-threaded)
        assert obj.access == obj._fast_access

    # cleanup: ensure SLOW_LOCKS back to True for other tests
    importlib.reload(settings)


def test_fast_access_vs_safe_same_result():
    """_safe_access and _fast_access must agree when no race (sanity)."""
    obj = Object.create(None, "test_access_eq")
    accessor = Object.create(None, "accessor")
    accessor.privilege_level = settings.Privilege.Player
    accessor.quelled = False
    obj.add_lock("test", lambda x: True)
    assert obj._safe_access(accessor, "test") == obj._fast_access(accessor, "test") is True
    obj.add_lock("test", lambda x: False)
    assert obj._safe_access(accessor, "test") == obj._fast_access(accessor, "test") is False


def test_concurrent_add_lock_vs_access_with_slow_locks_true():
    """Barrier `add_lock` vs `access` with SLOW_LOCKS=True (safe) — no RuntimeError."""
    import atheriz.settings as st
    with patch.object(st, "SLOW_LOCKS", True):
        obj = Object.create(None, "concurrent_safe")
        accessor = Object.create(None, "reader")
        accessor.privilege_level = settings.Privilege.Player
        accessor.quelled = False
        obj.add_lock("view", lambda x: True)

        barrier = threading.Barrier(2, timeout=5)
        errors: list[str] = []

        def writer():
            try:
                barrier.wait(timeout=5)
                for i in range(100):
                    obj.add_lock("view", lambda x, i=i: True)
            except Exception as e:
                errors.append(f"writer: {e!r}")

        def reader():
            try:
                barrier.wait(timeout=5)
                for _ in range(100):
                    obj.access(accessor, "view")
            except Exception as e:
                errors.append(f"reader: {e!r}")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert not errors, f"errors: {errors}"
        assert not t1.is_alive() and not t2.is_alive()


def test_gil_api_is_correct():
    """Public GIL detection API `sys._is_gil_enabled` exists and returns bool."""
    assert hasattr(sys, "_is_gil_enabled"), "sys._is_gil_enabled missing (expected in 3.13t+)"
    val = sys._is_gil_enabled()  # type: ignore[attr-defined]
    assert isinstance(val, bool)
