"""Regression tests for GameTime persistence robustness.

An alarm added by a game may carry arbitrary ``data`` -- GameTime.save() must
not be able to crash the save checkpoints (autosave / shutdown) when that
payload is not JSON-serializable, and ``save()`` must not race a concurrent
alarm mutation.
"""

import threading
import time
import tempfile

import pytest

from atheriz import settings
from atheriz.globals.time import GameTime
from atheriz.objects.base_obj import Object


def test_non_serializable_alarm_payload_does_not_crash_save(global_test_env):
    """GameTime.save() must tolerate alarm data that JSON cannot encode.

    add_alarm() accepts an arbitrary ``data`` (``Any``) documented as "data to
    pass to at_alarm()". json.dump raises TypeError on such payloads today,
    which fails the every-autosave tick and aborts GameTime.stop() during the
    shutdown sequence.
    """
    gt = GameTime()
    caller = Object.create(None, "timer")
    gt.add_alarm("7", "0", caller, repeat=True, data=object())

    gt.save()  # must not raise

    from pathlib import Path

    assert Path(settings.SAVE_PATH, "time").exists()


def test_save_must_serialize_with_alarm_mutations(global_test_env):
    """save() must hold the game-time lock so it can't race add_alarm()/on_tick().

    save() walks ``self.alarms`` and json.dumps it with no lock today; a
    concurrent alarm add mutates the dict mid-iteration (RuntimeError) and the
    file can be written against a half-mutated snapshot. The mutators all hold
    ``GameTime.lock``, so save() must block on the same lock: it must not
    complete while the lock is held by another thread.
    """
    gt = GameTime()
    caller = Object.create(None, "timer")
    gt.add_alarm("7", "0", caller, repeat=True, data="ok")

    errors = []

    def do_save():
        try:
            gt.save()
        except Exception as exc:
            errors.append(exc)

    with gt.lock:
        t = threading.Thread(target=do_save)
        t.start()
        time.sleep(0.2)
        finished_while_locked = not t.is_alive()
    t.join(timeout=5)

    assert errors == []
    assert finished_while_locked is False, (
        "save() completed while another thread held the game-time lock"
    )