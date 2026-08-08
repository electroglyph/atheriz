"""Issue tests: #30 — the short/alias dispatch path uses `text[:1]` unlowered
(inputfuncs.py:69, :87) while command keys are lowercase, and the reserved
single-letter guard list is lowercase too. A capitalized first letter therefore
behaves differently from its lowercase form.

INTENT: command lookup and the reserved/no-alias guard must be
case-insensitive on the first letter.
"""
from __future__ import annotations

from atheriz import settings
from atheriz.inputfuncs import dispatch_loggedin
from atheriz.objects.base_obj import Object


class _StubCmd:
    def access(self, caller):
        return True

    def execute(self, caller, cmd_args, cmdstring=""):
        return (self, caller, cmd_args)


class _StubCmdSet:
    """A cmdset that only knows the fallback 'none' command (nothing starts
    with 'n'), so the only way either input can resolve is through the short-
    alias path."""

    def get(self, key):
        if key == "none":
            return _StubCmd()
        return None

    def get_keys(self):
        return ["none"]


def test_capital_first_letter_obeys_no_alias_guard(global_test_env, monkeypatch):
    """INTENT: typing 'N' must be handled exactly like 'n' - the reserved
    single-letter movement guard blocks both. Today the unlowered 'N' escapes
    `_NO_ALIAS_COMMANDS` (inputfuncs.py:87) and cannot resolve -> FAIL."""
    monkeypatch.setattr(settings, "AUTO_COMMAND_ALIASING", True)
    monkeypatch.setattr(
        "atheriz.inputfuncs.get_loggedin_cmdset", lambda: _StubCmdSet()
    )

    puppet = Object.create(None, "walker")
    puppet.location = None

    # lowercase 'n' is blocked by the _NO_ALIAS_COMMANDS guard
    assert dispatch_loggedin(puppet, "n", immediate=True) is None

    # capitalized 'N' must be blocked identically
    result = dispatch_loggedin(puppet, "N", immediate=True)
    assert result is None, (
        f"capitalized first letter bypassed the no-alias guard and resolved a command: {result!r}"
    )