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

    def test_dunder_chain_denied(self, global_test_env):
        """INTENT: any dunder attribute walk (the classic `__subclasses__`
        escape ladder) must be rejected with a sandbox error."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        for code in (
            "caller.__class__.__mro__[1].__subclasses__()",
            "caller.__dict__",
            "(lambda: 0).__globals__",
            "().__class__",
            "x = 1\ny = x.__class__",
        ):
            c.msg.reset_mock()
            PyCommand().run(c, code)
            texts = _msg_texts(c)
            denied = [t for t in texts if "Error" in t and "dunder" in t]
            assert denied, f"{code!r} should be denied with a sandbox error, got {texts}"

    def test_benign_code_still_runs(self, global_test_env):
        """INTENT: the guard must not over-block ordinary non-dunder code."""
        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        PyCommand().run(c, "2 + 2")
        PyCommand().run(c, "caller.location")
        PyCommand().run(c, "x = [1]; x.append(2); x")

        combined = "\n".join(_msg_texts(c))
        assert "4" in combined
        assert "[1, 2]" in combined
        assert "Error" not in combined


class TestPyKill:
    def test_runaway_thread_is_killed(self, global_test_env, monkeypatch):
        """INTENT: with KILL_PY_COMMAND_AFTER set, an infinite loop must be
        force-killed via PyThreadState_SetAsyncExc, not just reported."""
        from atheriz.commands.loggedin import py as py_mod

        created = []
        orig_thread_cls = py_mod.threading.Thread

        class RecordingThread(orig_thread_cls):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        monkeypatch.setattr(py_mod.threading, "Thread", RecordingThread)
        monkeypatch.setattr(settings, "KILL_PY_COMMAND_AFTER", 0.2)

        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        PyCommand().run(c, "while True: pass")

        texts = _msg_texts(c)
        assert any("timed out" in t for t in texts), f"no timeout message, got {texts}"
        assert created, "worker thread was not created"
        assert not created[0].is_alive(), "killed worker thread must be dead"

    def test_zero_disables_kill(self, global_test_env, monkeypatch):
        """INTENT: KILL_PY_COMMAND_AFTER=0 disables the timeout entirely; a
        normal command runs to completion with no timed-out message."""
        monkeypatch.setattr(settings, "KILL_PY_COMMAND_AFTER", 0)

        c = Object.create(None, "Admin")
        c.privilege_level = settings.Privilege.Admin
        c.msg = MagicMock()

        PyCommand().run(c, "2 + 2")

        texts = _msg_texts(c)
        assert not any("timed out" in t for t in texts), texts
        assert any("4" in t for t in texts)
