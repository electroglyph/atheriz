"""Issue tests: deleting a tickable object never unregisters its `at_tick` from
the global ticker (`remove_coro` is only called from the `is_tickable` /
`tick_seconds` setters, never from `delete()`), so the deleted object keeps
ticking forever and the bound-method reference prevents GC (zombie ticks).
"""
from __future__ import annotations

from atheriz.globals.get import get_async_ticker
from atheriz.objects.base_obj import Object


def _ticker_coros(obj: Object) -> set:
    """Return the set of coros the global ticker has registered for `obj`."""
    at = get_async_ticker()
    slot = at.slots.get(obj._tick_seconds)
    return slot.coros if slot else set()


class TestDeleteUnregistersTickable:
    def test_delete_removes_tickable_from_ticker(self, global_test_env):
        """INTENT: deleting a tickable object must unregister its `at_tick` from
        the global ticker. The current implementation never calls `remove_coro`
        from `delete()`, so the deleted object's `at_tick` stays registered."""
        caller = Object.create(None, "caller")
        target = Object.create(None, "ticker", is_tickable=True)

        assert target.at_tick in _ticker_coros(target)

        target.delete(caller)

        assert target.at_tick not in _ticker_coros(target)

    def test_delete_keeps_other_tickables_registered(self, global_test_env):
        """Deleting one tickable must not disturb unrelated tickables."""
        caller = Object.create(None, "caller")
        target = Object.create(None, "ticker", is_tickable=True)
        survivor = Object.create(None, "survivor", is_tickable=True)

        target.delete(caller)

        assert target.at_tick not in _ticker_coros(target)
        assert survivor.at_tick in _ticker_coros(survivor)
