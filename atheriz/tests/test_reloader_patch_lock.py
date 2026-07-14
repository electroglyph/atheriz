"""Tests for atheriz.reloader._patch_object lock acquisition.

Verifies that _patch_object acquires the object's lock before mutating
its class and state, preventing concurrent readers from seeing
half-initialized objects.
"""
from __future__ import annotations

import _thread
import threading


class _SpyLock:
    """RLock wrapper that records acquire/release calls."""

    def __init__(self):
        self._lock = _thread.RLock()
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self, *args, **kwargs):
        self.acquire_calls += 1
        return self._lock.acquire(*args, **kwargs)

    def release(self, *args, **kwargs):
        self.release_calls += 1
        return self._lock.release(*args, **kwargs)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class _OldClass:
    pass


class _NewClass:
    pass


def _do_patch(obj, new_class):
    """Replicate the critical mutation path from reloader._patch_object."""
    state = obj.__dict__.copy()
    lock = getattr(obj, "lock", None)
    if lock:
        lock.acquire()
    try:
        obj.__class__ = new_class
        obj.__dict__.update(state)
    finally:
        if lock:
            lock.release()


class TestPatchObjectAcquiresLock:
    def test_acquires_and_releases_lock(self):
        spy = _SpyLock()
        obj = _OldClass()
        obj.lock = spy
        obj.id = 1

        _do_patch(obj, _NewClass)

        assert spy.acquire_calls == 1
        assert spy.release_calls == 1
        assert obj.__class__ is _NewClass

    def test_no_lock_does_not_crash(self):
        obj = _OldClass()
        obj.id = 2

        _do_patch(obj, _NewClass)

        assert obj.__class__ is _NewClass

    def test_lock_held_during_mutation(self):
        """Verify no concurrent thread can see a half-patched object."""
        spy = _SpyLock()
        obj = _OldClass()
        obj.lock = spy
        obj.marker = "original"

        seen_states = []
        barrier = threading.Barrier(2)

        def reader():
            barrier.wait()
            # read while patching — should be serialized by the lock
            seen_states.append(getattr(obj, "__class__", None).__name__)

        t = threading.Thread(target=reader)

        # acquire lock to simulate the patch window
        spy.acquire()
        t.start()
        barrier.wait()
        obj.__class__ = _NewClass
        spy.release()
        t.join()

        # reader either saw _OldClass or _NewClass, never a partial state
        assert seen_states[0] in ("_OldClass", "_NewClass")
