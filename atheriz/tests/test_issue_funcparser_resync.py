"""Issue tests: #44 — when a nested funcdef is executed, its return value is
merged back into the enclosing function's `infuncstr` (funcparser.py:547). The
old resync hack (`curr_func.rawstr = curr_func.rawstr[: -len(infuncstr)]`,
funcparser.py:386) stripped a post-execution-length chunk off the *raw* string,
and a pending nested return was silently dropped when the next `$` started
another nested funcdef.

Reproduced: ``parser.parse("$echo($inner()$inner())", escape=True)`` returned
``\\$echo(\\$inner())`` — the second ``$inner()`` was silently dropped from the
escaped output.

INTENT: escape/strip/reparse must preserve the full raw text of every nested
function.
"""
from __future__ import annotations

from atheriz.objects.funcparser import FuncParser


def _echo(*args, **kwargs):
    return "E"


def _inner(*args, **kwargs):
    return "RET"


def test_escape_preserves_consecutive_nested_funcdefs(global_test_env):
    parser = FuncParser({"echo": _echo, "inner": _inner})
    escaped = parser.parse("$echo($inner()$inner())", escape=True)
    assert escaped.count("$inner()") == 2, (
        "escape dropped a nested function; result lost raw text: "
        f"{escaped!r}"
    )


def test_escape_preserves_nested_funcdefs_with_surrounding_text(global_test_env):
    parser = FuncParser({"echo": _echo, "inner": _inner})
    escaped = parser.parse("$echo(a$inner()b$inner())", escape=True)
    assert escaped == r"\$echo(a\$inner()b\$inner())", escaped


def test_single_nested_escape_unchanged(global_test_env):
    parser = FuncParser({"echo": _echo, "inner": _inner})
    escaped = parser.parse("$echo($inner())", escape=True)
    assert escaped == r"\$echo(\$inner())", escaped


def test_normal_mode_preserves_both_nested_returns(global_test_env):
    captured = {}

    def echo(*args, **kwargs):
        captured["args"] = args
        return "E"

    parser = FuncParser({"echo": echo, "inner": _inner})
    parser.parse("$echo($inner()$inner())")
    assert captured["args"] == ("RETRET",), (
        "consecutive nested returns must both reach the enclosing function: "
        f"{captured['args']!r}"
    )


def test_unknown_func_fallback_keeps_both_nested_returns(global_test_env):
    parser = FuncParser({"inner": _inner})
    result = parser.parse("$echo($inner()$inner())")
    assert result.count("RET") == 2, (
        "unknown enclosing function must not drop nested returns: "
        f"{result!r}"
    )


def test_escaped_output_reparses_literal(global_test_env):
    calls = []

    def echo(*args, **kwargs):
        calls.append("echo")
        return "E"

    parser = FuncParser({"echo": echo, "inner": _inner})
    escaped = parser.parse("$echo($inner()$inner())", escape=True)
    assert calls == []
    reparsed = parser.parse(escaped)
    assert calls == [], "reparsed escaped output must not execute functions"
    assert reparsed == "$echo($inner()$inner())", reparsed
