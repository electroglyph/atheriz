from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from atheriz import utils


def test_word_replace_empty_and_full():
    with patch("atheriz.utils.uniform", return_value=1.0):
        assert utils.word_replace("hello world", 0) == "hello world"
    with patch("atheriz.utils.uniform", return_value=0.0):
        assert utils.word_replace("hello world", 1) == "... ..."
    with patch("atheriz.utils.uniform", return_value=0.0):
        assert utils.word_replace("hello world", 1, replacement="X") == "X X"
    with patch("atheriz.utils.uniform", return_value=1.0):
        assert utils.word_replace("", 1) == ""


def test_dice_zero_rolls_returns_zero():
    assert utils.dice_roll(0, 6) == 0
    assert utils.dice_roll(0, 0) == 0


def test_clamp_min_greater_than_max():
    assert utils.clamp(10, 5, 0) == 10
    assert utils.clamp(5, 10, 0) == 5
    assert utils.clamp(0, 5, 10) == 5
    assert utils.clamp(0, -5, 10) == 0
    assert utils.clamp(0, 15, 10) == 10


def test_strip_terminal_escapes_osc_null():
    assert utils.strip_terminal_escapes("\x1b[2J\x1b]0;title\x07\x00") == ""
    assert utils.strip_terminal_escapes("\x1b[31mhello\x1b[0m") == "hello"
    assert utils.strip_terminal_escapes("normal\x00text") == "normaltext"
    assert utils.strip_terminal_escapes("") == ""


def test_wrap_xterm256_ansi_codes_snapshot():
    result = utils.wrap_xterm256("hi", fg=196, bg=21, bold=True)
    assert "\x1b[38;5;196m" in result
    assert "\x1b[48;5;21m" in result
    assert "\x1b[1m" in result
    assert result.endswith("\x1b[0m")
    simple = utils.wrap_xterm256("hi", fg=5)
    assert "\x1b[38;5;5m" in simple
    cleared = utils.wrap_xterm256("\x1b[31mhi\x1b[0m", fg=1, clear=True)
    assert "\x1b[38;5;1m" in cleared


def test_compress_whitespace_max_spacing():
    assert utils.compress_whitespace("a    b", max_spacing=2) == "a  b"
    assert utils.compress_whitespace("a  b", max_spacing=1) == "a b"
    assert utils.compress_whitespace("a\n\n\nb", max_linebreaks=1) == "a\nb"
    assert utils.compress_whitespace("a \n\n b", max_linebreaks=1) == "a \n b"
    assert utils.compress_whitespace("  hello   world  ", max_spacing=2).strip() == "hello  world"


def test_ensure_thread_safe_idempotent():
    import threading

    class Dummy:
        def __init__(self):
            self.lock = threading.RLock()
            self.x = 1

    obj = Dummy()
    utils.ensure_thread_safe(obj)
    assert getattr(obj.__class__, "_is_thread_safe", False) is True
    orig_get = obj.__class__.__getattribute__
    orig_set = obj.__class__.__setattr__
    utils.ensure_thread_safe(obj)
    assert obj.__class__.__getattribute__ is orig_get
    assert obj.__class__.__setattr__ is orig_set
    obj.x = 5
    assert obj.x == 5
    obj.__class__._is_thread_safe = False


class TestEnsureThreadSafeNonwhitelistedMutables:
    def test_inplace_mutation_of_nonwhitelisted_mutable_marks_modified(self, global_test_env):
        """In-place mutation of a live non-whitelisted mutable must dirty the object.

        `_contents`/`hooks` are real engine stores missing from the 12-name
        copy whitelist, so `obj._contents` is returned live and `obj.__dict__`
        is returned live; mutating either bypasses `is_modified` (drops the
        change at the next `save_objects()` checkpoint) and races the lock.
        """
        from atheriz.objects.base_obj import Object

        obj = Object.create(None, "ThreadSafeAuditVictim")
        object.__setattr__(obj, "is_modified", False)
        obj._contents.add(987654321)
        assert object.__getattribute__(obj, "is_modified") is True, (
            "in-place obj._contents.add must set is_modified=True under lock"
        )
        object.__setattr__(obj, "is_modified", False)
        obj.__dict__["audit_sneaky_attr"] = 1
        assert object.__getattribute__(obj, "is_modified") is True, (
            "direct obj.__dict__ write must not bypass lock/dirty flag"
        )
        assert obj.audit_sneaky_attr == 1


class TestTrackedStoresMarkModified:
    def test_hooks_inplace_mutation_marks_modified(self, global_test_env):
        from atheriz.objects.base_obj import Object

        obj = Object.create(None, "HooksAuditVictim")
        object.__setattr__(obj, "is_modified", False)
        obj.hooks["audit_hook"] = set()
        assert object.__getattribute__(obj, "is_modified") is True
        assert obj.hooks["audit_hook"] == set()

    def test_node_links_nouns_inplace_mutation_marks_modified(self, global_test_env):
        from atheriz.globals.get import get_node_handler
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord

        nh = get_node_handler()
        node = Node(Coord("AuditArea", 0, 0, 0))
        nh.add_node(node)
        object.__setattr__(node, "is_modified", False)
        node.nouns["fountain"] = "A marble fountain."
        assert object.__getattribute__(node, "is_modified") is True
        assert node.nouns["fountain"] == "A marble fountain."

    def test_dict_view_copy_and_update_semantics(self, global_test_env):
        from atheriz.objects.base_obj import Object

        obj = Object.create(None, "DictViewVictim")
        # Reads behave like the real dict.
        assert obj.__dict__.copy() == object.__getattribute__(obj, "__dict__")
        assert dict(vars(obj))["name"] == "DictViewVictim"
        # Bulk restore through the view writes through (save-machinery path).
        object.__setattr__(obj, "is_modified", False)
        obj.__dict__.update({"view_key": "view_value"})
        assert obj.view_key == "view_value"
        assert object.__getattribute__(obj, "is_modified") is True

    def test_tracked_store_rebound_after_load(self, global_test_env):
        """A reloaded object's stores must notify again (owner rebound)."""
        from atheriz.objects.base_obj import Object
        from atheriz.globals.objects import (
            get,
            save_objects,
            load_objects,
        )
        from atheriz.globals import objects as obj_singleton

        obj = Object.create(None, "RebindVictim")
        chest = Object.create(None, "RebindChest")
        obj._contents.add(chest.id)
        save_objects()
        obj_singleton._ALL_OBJECTS.clear()
        load_objects()
        reloaded = get(obj.id)[0]
        object.__setattr__(reloaded, "is_modified", False)
        assert chest.id in reloaded._contents
        reloaded._contents.discard(chest.id)
        assert object.__getattribute__(reloaded, "is_modified") is True
        assert chest.id not in reloaded._contents
