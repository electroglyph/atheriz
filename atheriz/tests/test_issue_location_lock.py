"""Issue tests: room-to-room movement must lock the moving object's location."""
from __future__ import annotations

import subprocess
import sys


def test_room_move_locks_location_when_threadsafe_setters_are_disabled():
    """INTENT: movement remains safe without the optional setter patch."""
    child = r'''
from threading import RLock

from atheriz import settings
settings.THREADSAFE_GETTERS_SETTERS = False
settings.MAP_ENABLED = False

from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.commands.base_cmdset import CmdSet
from atheriz.utils import Coord


class TrackingLock:
    def __init__(self):
        self.lock = RLock()
        self.entries = 0

    def __enter__(self):
        self.lock.acquire()
        self.entries += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.lock.release()


source = Node(coord=Coord("test", 0, 0, 0), desc="Source")
destination = Node(coord=Coord("test", 1, 0, 0), desc="Destination")
obj = Object()
obj.internal_cmdset = CmdSet()
obj.external_cmdset = CmdSet()
obj.at_pre_move = lambda destination, to_exit=None, **kwargs: True
obj.at_post_move = lambda destination, to_exit=None, **kwargs: None
obj.move_to(source, announce=False)
tracker = TrackingLock()
obj.lock = tracker
assert obj.move_to(destination, announce=False)
print(tracker.entries)
'''
    result = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 1
