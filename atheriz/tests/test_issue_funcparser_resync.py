"""Issue tests: #44 — when a nested funcdef is executed, its return value is
merged back into the enclosing function's `infuncstr` (funcparser.py:547). The
resync hack (`curr_func.rawstr = curr_func.rawstr[: -len(infuncstr)]`,
funcparser.py:386) then strips that many chars from the *raw* string, but the
prefix may differ in length from the executed result, so the enclosing function
loses ar: raw text.

Reproduced: ``parser.parse("$echo($inner()$inner())", escape=True)`` returns
``\\$echo(\\$inner())`` — the second ``$inner()`` is silently dropped from the
escaped output (only the return values make it work for the non-escape path).

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