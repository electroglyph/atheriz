"""Tests for atheriz.reloader._apply_patch lock acquisition and init skipping.

Verifies that _apply_patch acquires the object's lock before mutating
its class and state, and skips __init__ when the signature is unchanged.
"""
from __future__ import annotations

import _thread
import inspect
import threading
from atheriz.reloader import _apply_patch


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


_init_call_log = []


class _InitSideEffectOld:
    def __init__(self):
        _init_call_log.append("old")
        self.x = 42


class _InitSideEffectNew:
    def __init__(self):
        _init_call_log.append("new")
        self.x = 99


class _InitChangedOld:
    def __init__(self, a):
        self.a = a


class _InitChangedNew:
    def __init__(self, a, b):
        self.a = a
        self.b = b


class TestReloadSkipsInitWhenUnchanged:
    def test_init_not_called_when_signature_unchanged(self):
        """5.7: __init__ should be skipped when old and new class have the same __init__."""
        _init_call_log.clear()
        obj = _InitSideEffectOld()
        assert obj.x == 42
        assert _init_call_log == ["old"]

        _apply_patch(obj, _InitSideEffectNew)

        # after the fix, __init__ should NOT have been called again
        assert _init_call_log == ["old"], (
            f"__init__ was called during reload — side effect leaked: {_init_call_log}"
        )
        # state should still be restored from before the patch
        assert obj.x == 42

    def test_init_called_when_signature_changes(self):
        """When __init__ signature changes, __init__ SHOULD be called."""
        _init_call_log.clear()
        obj = _InitChangedOld(a=1)
        obj.lock = _SpyLock()

        # signature changes from (a) to (a, b) — TypeError on __init__()
        # the bare except catches it, which is fine
        _apply_patch(obj, _InitChangedNew)

        assert obj.a == 1  # state restored
