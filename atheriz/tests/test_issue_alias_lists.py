"""Issue tests: #41 — `commands/loggedin/none.py` `_IGNORED_COMMANDS` and
`inputfuncs.py` `_IGNORE_KEYS` are meant to be the same safety list: keys the
resolver refuses to auto-alias (inputfuncs.py:91) should be exactly the commands
`none` excludes from its "did you mean?" suggestion list (none.py:29-34).

They have diverged (e.g. ``wander``/``exit``/``logout``/``disconnect`` are in
``_IGNORE_KEYS`` but not ``_IGNORED_COMMANDS``), so a user is *suggested* a
command that auto-alias then refuses to resolve.

INTENT: both lists are derived from a single source of truth and agree.
"""
from __future__ import annotations
from unittest.mock import MagicMock

import atheriz.inputfuncs as inputfuncs
from atheriz import settings
from atheriz.commands.loggedin.none import _IGNORED_COMMANDS
from atheriz.commands.loggedin.none import NoneCommand
from atheriz.commands.unloggedin.none import NoneCommand as UnloggedinNoneCommand
from atheriz.inputfuncs import dispatch_loggedin, _resolve_unloggedin
from atheriz.objects.base_obj import Object


class _StubCmd:
    key = "stub"

    def access(self, caller):
        return True

    def execute(self, caller, cmd_args, cmdstring=""):
        return (self, caller, cmd_args)


class _BlocklistCmdSet:
    """A cmdset with a blocklisted key, a benign key, and the none fallback."""

    def __init__(self, keys):
        self.cmds = {}
        for key in keys:
            cmd = _StubCmd()
            cmd.key = key
            self.cmds[key] = cmd

    def get(self, key):
        return self.cmds.get(key)

    def get_keys(self):
        return list(self.cmds.keys())


def test_alias_blocklist_matches_none_suggestions(global_test_env):
    """INTENT: the commands auto-alias is forbidden from resolving
    (``_IGNORE_KEYS``) must be exactly the commands ``none`` withholds from its
    spell suggestions. Today they disagree -> the suggestions recommend commands
    the resolver refuses."""
    assert set(_IGNORED_COMMANDS) == set(inputfuncs._IGNORE_KEYS), (
        "none suggestion blocklist drifted from the auto-alias blocklist: "
        f"none_ignored={_IGNORED_COMMANDS!r} inputfuncs._IGNORE_KEYS={inputfuncs._IGNORE_KEYS!r}"
    )


def test_auto_alias_ignored_keys_are_withheld_from_suggestions(global_test_env):
    """Every key auto-alias refuses (``_IGNORE_KEYS``) must also be withheld
    from the none command's suggestions, so a suggestion can always actually be
    typed and resolved."""
    assert set(inputfuncs._IGNORE_KEYS) <= set(_IGNORED_COMMANDS), (
        "auto-alias refused commands that 'none' still suggests: "
        f"{set(inputfuncs._IGNORE_KEYS) - set(_IGNORED_COMMANDS)}"
    )


def test_auto_alias_never_resolves_blocklisted_key(global_test_env, monkeypatch):
    """INTENT: typing a prefix of a blocklisted command must never auto-alias
    to it; the input falls through to the none fallback instead."""
    monkeypatch.setattr(settings, "AUTO_COMMAND_ALIASING", True)
    cmdset = _BlocklistCmdSet(["quit", "look", "none"])
    monkeypatch.setattr("atheriz.inputfuncs.get_loggedin_cmdset", lambda: cmdset)

    puppet = Object.create(None, "walker")
    puppet.location = None

    result = dispatch_loggedin(puppet, "qu", immediate=True)
    assert result is not None
    assert result[0] is cmdset.cmds["none"]
    assert result[2] == "qu"

    resolved = dispatch_loggedin(puppet, "lo", immediate=True)
    assert resolved is not None
    assert resolved[0] is cmdset.cmds["look"]


def test_none_suggestions_withhold_blocklisted_keys(global_test_env, monkeypatch):
    """INTENT: the "did you mean?" suggestion must never name a blocklisted
    command, so every suggestion is actually typeable and resolvable."""
    monkeypatch.setattr(
        "atheriz.commands.loggedin.none.get_loggedin_cmdset",
        lambda: _BlocklistCmdSet(["quit", "save", "look", "help", "none"]),
    )

    caller = MagicMock()
    caller.internal_cmdset = None
    args = MagicMock(none=["qu"])
    NoneCommand().run(caller, args)

    msg = caller.msg.call_args.args[0]
    assert "did you mean" in msg
    assert "quit" not in msg
    assert "save" not in msg
    assert "none" not in msg


def test_unloggedin_auto_alias_never_resolves_blocklisted_key(global_test_env, monkeypatch):
    """INTENT: the unloggedin resolver applies the same blocklist: a prefix of
    'quit' must not auto-alias to it."""
    monkeypatch.setattr(settings, "AUTO_COMMAND_ALIASING", True)
    cmdset = _BlocklistCmdSet(["quit", "new", "none"])
    monkeypatch.setattr("atheriz.inputfuncs.get_unloggedin_cmdset", lambda: cmdset)

    connection = MagicMock()
    result = _resolve_unloggedin(connection, "qu")
    assert result is not None
    assert result[0] is cmdset.cmds["none"]


def test_unloggedin_none_suggestions_withhold_blocklisted_keys(global_test_env, monkeypatch):
    """INTENT: the unloggedin "did you mean?" fallback also withholds
    blocklisted commands from its suggestions."""
    cmdset = MagicMock()
    cmdset.commands.keys.return_value = ["quit", "exit", "logout", "disconnect", "connect", "new"]
    monkeypatch.setattr(
        "atheriz.commands.unloggedin.none.get_unloggedin_cmdset", lambda: cmdset
    )

    caller = MagicMock()
    args = MagicMock(none=["quut"])
    UnloggedinNoneCommand().run(caller, args)

    msg = caller.msg.call_args.args[0]
    assert "did you mean" in msg
    assert "quit" not in msg
    assert "exit" not in msg
    assert "logout" not in msg
    assert "disconnect" not in msg