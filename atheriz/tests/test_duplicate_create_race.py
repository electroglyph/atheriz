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


def _gated(monkeypatch):
    """Gate `add_object_unique` so both racing threads enter the atomic
    check+insert only after both have reached it, then run it through to
    completion; the loser must observe the winner's registration."""
    import atheriz.globals.objects as store

    gate = threading.Barrier(2)
    orig = store.add_object_unique

    def gated(*args, **kwargs):
        gate.wait(timeout=10)
        return orig(*args, **kwargs)

    monkeypatch.setattr(store, "add_object_unique", gated)
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
    _gated(monkeypatch)
    name = "shared_account_name"

    outcomes = _run_race(lambda: Account.create(name, "password123"))

    created = [o for o in outcomes if o]
    assert len(outcomes) == 2
    # INTENT: exactly one creation wins; the loser raises ValueError.
    assert len(created) == 1, f"both racing creates succeeded: {outcomes}"
    assert len(outcomes) - len(created) == 1, "loser did not raise"


def test_concurrent_channel_create_has_name(global_test_env, monkeypatch):
    _gated(monkeypatch)
    name = "unique_channel_name"

    outcomes = _run_race(lambda: Channel.create(name))

    created = [o for o in outcomes if o]
    assert len(outcomes) == 2
    assert len(created) == 1, f"both racing creates succeeded: {len(created)}"
    assert len(outcomes) - len(created) == 1, "loser did not raise ValueError"