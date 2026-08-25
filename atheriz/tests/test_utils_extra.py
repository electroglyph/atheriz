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
