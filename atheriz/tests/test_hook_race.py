"""Issue tests: hook dispatch must not iterate a set while it is mutated."""
from __future__ import annotations

import threading
import time
from threading import RLock

from atheriz.objects.base_obj import hookable


class _BlockingSet(set):
    def __init__(self, values=()):
        super().__init__(values)
        self.first_yielded = threading.Event()
        self.release = threading.Event()

    def __iter__(self):
        iterator = super().__iter__()
        try:
            first = next(iterator)
        except StopIteration:
            return
        yield first
        self.first_yielded.set()
        if not self.release.wait(timeout=2):
            raise AssertionError("hook iteration was not released")
        yield from iterator


class _Hook:
    is_before = True
    is_after = False
    is_replace = False

    def __call__(self, *args, **kwargs):
        pass


class _Target:
    def __init__(self, hooks):
        self.lock = RLock()
        self.hooks = {"run": hooks}

    @hookable
    def run(self):
        pass


def test_hook_dispatch_snapshots_before_concurrent_mutation():
    """INTENT: a hook set changing under its owner's lock cannot break dispatch."""
    first = _Hook()
    second = _Hook()
    hook_set = _BlockingSet([first])
    target = _Target(hook_set)
    errors = []

    def invoke():
        try:
            target.run()
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=invoke)
    worker.start()
    assert hook_set.first_yielded.wait(timeout=2)

    def mutate():
        with target.lock:
            hook_set.add(second)

    mutator = threading.Thread(target=mutate)
    mutator.start()
    time.sleep(0.05)
    hook_set.release.set()
    worker.join(timeout=2)
    mutator.join(timeout=2)

    assert not worker.is_alive()
    assert not mutator.is_alive()
    assert errors == []
