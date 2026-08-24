"""Issue tests: set/unset crash on read-only properties; py builder gate.

`set`/`unset` call `setattr`/`delattr` with no guard, so targeting a read-only
property (e.g. `is_builder`, `is_superuser`) raises an unhandled AttributeError
that the threadpool only swallows into a log — the player gets no response.
Separately, `py` was gated at superuser while `set`/`unset`/`ban`/`unban` are
builder-gated; `py` is now builder-accessible like the rest.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from atheriz import settings
from atheriz.commands.loggedin.py import PyCommand
from atheriz.commands.loggedin.set import SetCommand, UnsetCommand
from atheriz.objects.base_obj import Object


class TestSetUnsetReadOnlyProps:
    def _caller(self):
        c = Object.create(None, "Alice")
        c.privilege_level = settings.Privilege.Builder
        c.quelled = False
        c.msg = MagicMock()
        return c

    def test_set_readonly_property_refused_not_crash(self, global_test_env):
        """INTENT: `set me is_builder` must refuse with a message, not raise
        AttributeError (which the threadpool swallows, leaving no response)."""
        c = self._caller()
        SetCommand().run(c, MagicMock(target="me", attribute="is_builder", value="True"))
        texts = [str(a[0]) for a, _ in c.msg.call_args_list]
        assert any("read-only" in t for t in texts)
        assert c.is_builder is True

    def test_unset_readonly_property_refused_not_crash(self, global_test_env):
        """INTENT: `unset me is_superuser` must refuse with a message, not
        raise AttributeError."""
        c = self._caller()
        UnsetCommand().run(c, MagicMock(target="me", attribute="is_superuser"))
        texts = [str(a[0]) for a, _ in c.msg.call_args_list]
        assert any("read-only" in t for t in texts)


class TestPyBuilderGate:
    def _obj(self, privilege):
        c = Object.create(None, "Admin")
        c.privilege_level = privilege
        c.quelled = False
        return c

    def test_builder_can_access_py(self, global_test_env):
        """INTENT: `py` is builder-accessible (consistent with set/unset/ban)."""
        assert PyCommand().access(self._obj(settings.Privilege.Builder)) is True

    def test_player_denied(self, global_test_env):
        assert PyCommand().access(self._obj(settings.Privilege.Player)) is False
