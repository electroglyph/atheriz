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

import atheriz.inputfuncs as inputfuncs
from atheriz.commands.loggedin.none import _IGNORED_COMMANDS


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