"""Issue tests: #46 — `NodeHandler.save` and `MapHandler.save` deep-copy their
in-memory areas / map data before serializing (node.py:73-77, map.py:382). Any
value carrying a non-deepcopyable lock would abort the save; the concern is a
RLock-bearing value parked in map data.

Verification against the current code: a bare ``copy.deepcopy(threading.RLock())``
raises ``TypeError: cannot pickle '_thread.RLock' object``, but ``MapInfo``
defines ``__getstate__``/``__setstate__`` (map.py:87-101) that drop the lock,
so today the map is safe. This test pins that regression: a deepcopy of a live
MapInfo must not raise even though RLock cannot be pickled directly.
"""
from __future__ import annotations

import copy

from atheriz.globals.map import MapInfo, MapHandler


def test_mapinfo_deepcopy_survives_rlock(global_test_env):
    mi = MapInfo(name="area", pre_grid={(0, 0): "*"}, post_grid={(0, 0): "."})
    clone = copy.deepcopy(mi)
    assert clone.pre_grid == {(0, 0): "*"}
    assert isinstance(clone.lock, type(mi.lock))