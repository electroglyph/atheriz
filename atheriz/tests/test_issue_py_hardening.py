"""Issue tests: layered `py` sandbox hardening.

Closes the known escape gaps: non-dunder interpreter introspection attributes
(gi_frame/f_back/f_builtins/...), constant-string subscript indirection,
raw-module traversal, the str.format field-syntax escape, literal bombs
(9**9**9, giant string repeats), imports, oversized programs, unbounded CPU,
and unbounded stdout. Every attribute load in user code is rewritten to a
guarded runtime call (_attr), modules are replaced by whitelist proxies, and
execution runs under a line-event budget with a per-server single-flight lock.
"""

from __future__ import annotations

import logging
import threading

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin import py as py_mod
from atheriz.commands.loggedin.py import PyCommand
from atheriz.logger import logger
from atheriz.objects.base_obj import Object
from atheriz.utils import strip_ansi


def _msg_texts(caller) -> list[str]:
    out = []
    for call in caller.msg.call_args_list:
        args, kwargs = call
        if args:
            out.append(strip_ansi(str(args[0])))
        elif "text" in kwargs and kwargs["text"] is not None:
            out.append(strip_ansi(str(kwargs["text"])))
    return out


def _last_msg(caller) -> str:
    return _msg_texts(caller)[-1]


@pytest.fixture
def caller(global_test_env):
    c = Object.create(None, "Admin")
    c.privilege_level = settings.Privilege.Admin
    c.msg = MagicMock()
    yield c


class TestEscapePayloads:
    """Known escape chains must be denied without side effects."""

    @pytest.mark.parametrize("code", [
        "g = (x for x in [1])\ng.gi_frame",
        "(x for x in [1]).gi_frame.f_back",
        "(lambda: 0).__globals__",
        "try:\n    1/0\nexcept Exception as e:\n    e.__traceback__.tb_frame",
        'getattr(caller, "gi_frame")',
        'getattr(caller, "__class__")',
        '"{0.__class__.__base__}".format(caller)',
        '"{}".format_map(caller.__dict__)'.replace("caller.__dict__", "caller"),
        '{"a": 1}["__class__"]',
        'd = {"format": 1}\nd["format"]',
        "f\"{caller.__class__}\"",
    ])
    def test_escape_chains_denied(self, caller, code):
        PyCommand().run(caller, code)
        text = _last_msg(caller)
        assert "Error" in text, f"{code!r} unexpectedly succeeded: {text!r}"
        assert not any("<class" in t or "'frame'" in t for t in _msg_texts(caller))

    def test_generator_frame_walk_no_side_effect(self, caller, tmp_path):
        marker = tmp_path / "pwned_marker"
        payload = (
            "g = (x for x in [1])\n"
            f"g.gi_frame.f_back.f_builtins['__import__']('os').system('touch {marker}')"
        )
        PyCommand().run(caller, payload)
        assert "Error" in _last_msg(caller)
        assert not marker.exists()

    def test_module_proxies_block_traversal(self, caller):
        for code in (
            "time.sleep",
            "pprint.sys",
            "settings.THREADPOOL_LIMIT",
            "time.time.__globals__",
        ):
            caller.msg.reset_mock()
            PyCommand().run(caller, code)
            assert "Error" in _last_msg(caller), f"{code!r} not denied"

    def test_imports_rejected(self, caller):
        for code in ("import os", "from os import system"):
            caller.msg.reset_mock()
            PyCommand().run(caller, code)
            assert "imports are not permitted" in _last_msg(caller)

    def test_attribute_store_rejected(self, caller):
        PyCommand().run(caller, "caller.name = 'hacked'")
        assert "Error" in _last_msg(caller)
        assert caller.name == "Admin"

    def test_settings_mutation_rejected(self, caller):
        before = settings.PY_OUTPUT_FG
        PyCommand().run(caller, "settings.PY_OUTPUT_FG = 5")
        assert settings.PY_OUTPUT_FG == before

    def test_chained_exponentiation_blocked(self, caller):
        PyCommand().run(caller, "9**9**9")
        text = _last_msg(caller)
        assert "Error" in text
        assert ("blocked" in text) or ("too large" in text)

    def test_giant_string_repeat_blocked(self, caller):
        PyCommand().run(caller, "'a' * (10**12)")
        assert "too large" in _last_msg(caller)

    def test_oversized_program_rejected(self, caller):
        PyCommand().run(caller, " + ".join(str(i) for i in range(30000)))
        assert "Error" in _last_msg(caller)

    def test_code_byte_cap(self, caller, monkeypatch):
        monkeypatch.setattr(settings, "PY_MAX_CODE_BYTES", 4)
        PyCommand().run(caller, "1 + 1")
        assert "too long" in _last_msg(caller)


class TestExecutionBudget:
    def test_line_budget_kills_infinite_loop(self, caller, monkeypatch):
        """With the wall-clock timeout disabled, the line-event budget must
        still stop an infinite loop deterministically."""
        monkeypatch.setattr(settings, "KILL_PY_COMMAND_AFTER", 0)
        monkeypatch.setattr(settings, "PY_MAX_LINE_EVENTS", 100_000)

        PyCommand().run(caller, "while True: pass")

        text = _last_msg(caller)
        assert "timed out" in text

    def test_lock_released_after_timeout(self, caller, monkeypatch):
        """A killed run must release the single-flight lock so later runs work."""
        monkeypatch.setattr(settings, "KILL_PY_COMMAND_AFTER", 0)
        monkeypatch.setattr(settings, "PY_MAX_LINE_EVENTS", 100_000)

        PyCommand().run(caller, "while True: pass")

        caller.msg.reset_mock()
        PyCommand().run(caller, "2 + 2")
        texts = _msg_texts(caller)
        assert any("-- int --" in t for t in texts)
        assert not any("still running" in t for t in texts)

    def test_single_flight_refuses_concurrent_run(self, caller):
        held = py_mod._SANDBOX_LOCK.acquire(blocking=False)
        try:
            assert held
            PyCommand().run(caller, "2 + 2")
            assert "still running" in _last_msg(caller)
        finally:
            py_mod._SANDBOX_LOCK.release()

    def test_bounded_stdout_writer(self, caller, monkeypatch):
        """A print flood must cap buffer growth instead of exhausting memory."""
        monkeypatch.setattr(settings, "PY_MAX_OUTPUT_LINES", 1000000)
        monkeypatch.setattr(settings, "PY_MAX_OUTPUT_BYTES", 1000000)

        PyCommand().run(caller, "for i in range(20000):\n    print('x' * 100)")

        text = "\n".join(_msg_texts(caller))
        assert "[truncated:" in text


class TestAccessGating:
    def test_builder_allowed_by_default(self, caller):
        caller.privilege_level = settings.Privilege.Builder
        assert PyCommand().access(caller) is True

    def test_require_superuser_blocks_builder(self, caller, monkeypatch):
        monkeypatch.setattr(settings, "PY_REQUIRE_SUPERUSER", True)
        caller.privilege_level = settings.Privilege.Builder
        assert PyCommand().access(caller) is False

    def test_require_superuser_allows_superuser(self, caller, monkeypatch):
        monkeypatch.setattr(settings, "PY_REQUIRE_SUPERUSER", True)
        caller.privilege_level = settings.Privilege.Admin
        assert PyCommand().access(caller) is True


class TestDenialAuditLog:
    def test_denial_logged_at_warning(self, caller, tmp_path):
        log_file = tmp_path / "py_denials.log"
        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)
        try:
            PyCommand().run(caller, "caller.__class__")
            handler.flush()
            content = log_file.read_text()
            assert "py sandbox denied" in content
            assert "dunder" in content
        finally:
            logger.removeHandler(handler)
            handler.close()


class TestLegitimateUseStillWorks:
    @pytest.mark.parametrize("code,expect", [
        ("2 + 2", "4"),
        ("[x * 2 for x in range(3)]", "[0, 2, 4]"),
        ("print('hello')", "hello"),
        ("caller.name", "Admin"),
        ("x = [1]\nx.append(2)\nx", "[1, 2]"),
        ("search('nothing-matches-this')", "[]"),
        ("get(caller.id)[0] is caller", "True"),
        ("settings.PY_OUTPUT_FG", str(settings.PY_OUTPUT_FG)),
        ("isinstance(time.time(), float)", "True"),
        ("pprint.pformat({'a': 1})", "'a': 1"),
        ("getattr(caller, 'nope', 'fallback')", "fallback"),
    ])
    def test_still_runs(self, caller, code, expect):
        caller.msg.reset_mock()
        PyCommand().run(caller, code)
        combined = "\n".join(_msg_texts(caller))
        assert expect in combined, f"{code!r}: expected {expect!r} in {combined!r}"
        assert "Error" not in combined, f"{code!r} raised: {combined!r}"

    def test_trailing_expression_capture(self, caller):
        PyCommand().run(caller, "y = 21\ny * 2")
        assert any("-- int --" in t and "42" in t for t in _msg_texts(caller))
