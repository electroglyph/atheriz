"""Regression tests for GameTime persistence robustness.

Alarm ``data`` is now enforced to be a dict (or None) at add_alarm() time so
GameTime.save() can never hit a json.dump TypeError during save checkpoints
(autosave / shutdown), and save() must not race a concurrent alarm mutation.
"""

import threading
import time
import tempfile

import pytest

from atheriz import settings
from atheriz.globals.time import GameTime
from atheriz.objects.base_obj import Object


def test_non_dict_alarm_data_is_rejected(global_test_env):
    """add_alarm() must refuse anything that is not a dict or None."""
    gt = GameTime()
    caller = Object.create(None, "timer")

    with pytest.raises(TypeError):
        gt.add_alarm("7", "0", caller, repeat=True, data=object())

    assert gt.alarms == {}


def test_dict_alarm_data_saves_without_error(global_test_env):
    """GameTime.save() must succeed with dict alarm data."""
    gt = GameTime()
    caller = Object.create(None, "timer")
    gt.add_alarm("7", "0", caller, repeat=True, data={"key": "val"})

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
    gt.add_alarm("7", "0", caller, repeat=True)

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