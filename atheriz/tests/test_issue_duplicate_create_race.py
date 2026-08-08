"""Issue tests: #22 (+ #42) — `Account.create` / `Channel.create` do a
check-then-insert for single-name uniqueness in separate critical sections, so
two threads can create same-named accounts or channels at the same moment and
``INSERT OR REPLACE`` at save time stores both.

INTENT: exactly one object with a given name may ever be created; the racing
loser must raise the duplicate error.
"""
from __future__ import annotations

import threading

from atheriz.objects.base_account import Account
from atheriz.objects.base_channel import Channel


def _gated(monkeypatch, module_name):
    """Gate `add_object` so both racing threads reach the insert while the
    store still holds no entries (making the race window deterministic)."""
    import importlib

    mod = importlib.import_module(module_name)
    gate = threading.Barrier(2)
    orig = mod.add_object

    def gated(obj):
        gate.wait(timeout=10)
        return orig(obj)

    monkeypatch.setattr(mod, "add_object", gated)
    return gate


def _run_race(fn):
    barrier = threading.Barrier(2)
    outcomes = []

    def worker():
        barrier.wait()
        try:
            fn()
            outcomes.append(True)
        except ValueError:
            outcomes.append(False)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    return outcomes


def test_concurrent_account_create_same_name(global_test_env, monkeypatch, fixed_salt):
    _gated(monkeypatch, "atheriz.objects.base_account")
    name = "shared_account_name"

    outcomes = _run_race(lambda: Account.create(name, "password123"))

    created = [o for o in outcomes if o]
    assert len(outcomes) == 2
    # INTENT: exactly one creation wins; the loser raises ValueError.
    assert len(created) == 1, f"both racing creates succeeded: {outcomes}"
    assert len(outcomes) - len(created) == 1, "loser did not raise"


def test_concurrent_channel_create_has_name(global_test_env, monkeypatch):
    _gated(monkeypatch, "atheriz.objects.base_channel")
    name = "unique_channel_name"

    outcomes = _run_race(lambda: Channel.create(name))

    created = [o for o in outcomes if o]
    assert len(outcomes) == 2
    assert len(created) == 1, f"both racing creates succeeded: {len(created)}"
    assert len(outcomes) - len(created) == 1, "loser did not raise ValueError"