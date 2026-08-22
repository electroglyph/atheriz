"""Issue tests: TOCTOU creating duplicate MapInfo.

MapHandler's lazy-creation paths did the existence lookup under self.lock but
constructed the new MapInfo and inserted it via set_mapinfo() outside the lock.
Two threads entering the same never-seen (area, z) could each build a distinct
MapInfo; the second set_mapinfo overwrote the first, stranding the loser's
listeners/mapables on an unreachable instance (and persisting whichever
instance won). Fixed with an atomic _get_or_create helper; all four call sites
route through it.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from atheriz.globals.map import MapHandler, MapInfo


def _loc(area: str, z: int = 0):
    loc = MagicMock()
    loc.coord.area = area
    loc.coord.z = z
    return loc


@pytest.fixture
def handler(global_test_env):
    return MapHandler()


class TestConcurrentFirstEntry:
    def test_move_listener_and_mapable_share_one_instance(self, handler):
        """INTENT: a listener and a mapable arriving in the same fresh area
        concurrently must end up registered on ONE MapInfo instance."""
        area = "race-area"
        listener = MagicMock()
        listener.id = "L1"
        listener.location = _loc(area)
        mapable = MagicMock()
        mapable.id = "M1"
        mapable.location = _loc(area)

        barrier = threading.Barrier(2, timeout=5)

        def run(fn, ent):
            barrier.wait()
            fn(ent)

        with ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(run, handler.add_listener, listener)
            f2 = ex.submit(run, handler.add_mapable, mapable)
            f1.result(10)
            f2.result(10)

        chunks = [v for k, v in handler.data.items() if k == (area, 0)]
        assert len(chunks) == 1
        mi = chunks[0]
        assert listener.id in mi.listeners
        assert mapable.id in mi.objects

    def test_overlapping_constructions_yield_single_instance(self, handler):
        """INTENT: when two threads race creation and construction is slow,
        they still observe exactly one instance per key."""
        orig_init = MapInfo.__init__
        area = "slow-area"

        def slow_init(self, *a, **k):
            orig_init(self, *a, **k)
            time.sleep(0.05)

        results: list = []
        barrier = threading.Barrier(2, timeout=5)

        def creator():
            barrier.wait()
            results.append(handler._get_or_create(area, 0))

        with patch.object(MapInfo, "__init__", slow_init):
            with ThreadPoolExecutor(max_workers=2) as ex:
                f1 = ex.submit(creator)
                f2 = ex.submit(creator)
                f1.result(10)
                f2.result(10)

        assert len(results) == 2
        assert results[0] is results[1]
        assert [k for k in handler.data if k[0] == area] == [(area, 0)]


class TestExistingKeyIdentity:
    def test_get_or_create_returns_existing_object_unchanged(self, handler):
        """INTENT: get-or-create on an existing key must return the identical
        instance and never overwrite it."""
        mi = MapInfo(name="existing")
        mi.pre_grid[(0, 0)] = "#"
        mi.post_grid[(0, 0)] = "+"
        handler.set_mapinfo("existing", 3, mi)

        got = handler._get_or_create("existing", 3)

        assert got is mi
        assert mi.pre_grid[(0, 0)] == "#"
        assert mi.post_grid[(0, 0)] == "+"


class TestPersistenceCoherence:
    def test_save_reload_yields_single_chunk(self, handler):
        """INTENT: after a raced creation, the persisted state must contain
        exactly one chunk for the key — no losing duplicate can be saved.
        (listeners/objects are deliberately not serialized; MapInfo.__getstate__
        drops them, they are rebuilt as objects enter the area.)"""
        area = "persist-area"
        listener = MagicMock()
        listener.id = "L1"
        listener.location = _loc(area)
        mapable = MagicMock()
        mapable.id = "M1"
        mapable.location = _loc(area)

        handler.add_listener(listener)
        handler.add_mapable(mapable)
        assert listener.id in handler.get_mapinfo(area, 0).listeners

        handler.save()

        reloaded = MapHandler()
        chunks = [v for k, v in reloaded.data.items() if k == (area, 0)]
        assert len(chunks) == 1
        assert chunks[0].name == area
