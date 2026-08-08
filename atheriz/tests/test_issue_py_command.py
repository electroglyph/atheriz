"""Issue tests: `py` re-evaluates the last expression statement after exec'ing
it, so side effects (e.g. print) run twice.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.py import PyCommand
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


class TestPyDoubleEval:
    def test_last_expression_runs_once(self, global_test_env):
        """INTENT: in `x = 1; print(x)`, the print must execute exactly once.
        The current code exec's the whole tree (printing once) and then
        re-evals the trailing Expr, printing a second time."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        PyCommand().run(c, "x = 1\nprint(x)")

        stdout_lines = [
            line
            for text in _msg_texts(c)
            for line in text.split("\n")
            if line == "1"
        ]
        assert stdout_lines == ["1"]

    def test_single_expression_runs_once(self, global_test_env):
        """Sanity: a single expression must not be double-evaluated either."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        PyCommand().run(c, "print('hi')")

        stdout_lines = [
            line
            for text in _msg_texts(c)
            for line in text.split("\n")
            if line == "hi"
        ]
        assert stdout_lines == ["hi"]


class TestPySandboxEscape:
    def test_dunder_attribute_walk_denied(self, global_test_env):
        """INTENT: the py sandbox must not let a Builder reach private objects
        through dunder attribute access (`caller.__class__.__mro__[1]
        .__subclasses__()` -> os.system, importlib, ...). Only getattr()
        *calls* are blacklisted today; plain `.<attr>` loads are not."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        PyCommand().run(c, "caller.__class__")

        texts = _msg_texts(c)
        assert any("Error" in t for t in texts), f"dunder access should be denied, got {texts}"
        assert not any("<class " in t for t in texts), f"sandbox leaked a class object: {texts}"

    def test_bad_builtins_lookup_denied(self, global_test_env):
        """INTENT: lookups outside the whitelisted globals/`__builtins__` must
        be denied (os, subprocess, importlib, open, compile...)."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        for code in ("__import__('os')", "open('/etc/passwd')", "eval('1+1')"):
            c.msg.reset_mock()
            PyCommand().run(c, code)
            texts = _msg_texts(c)
            errors = [
                t for t in texts
                if t.startswith("Error:") or "named 'os'" in t or "not defined" in t or "is not defined" in t
            ]
            assert errors, f"{code!r} unexpectedly succeeded: {texts}"
