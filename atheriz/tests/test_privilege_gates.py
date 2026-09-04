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


class TestDeletePrivilegeGate:
    def test_builder_cannot_delete_equal_or_higher_privilege_object(self, global_test_env):
        """Builder delete must refuse equal/higher-privilege targets like set does.

        `delete` only checks the `delete` access lock (which blocks just
        self-delete), so a builder in the same room can delete an equal- or
        higher-privilege object/PC. Mirror `set.py` `_privilege_denied`
        (`t_priv >= c_priv`): refuse with a message and leave the target alive.
        """
        from unittest.mock import MagicMock

        from atheriz.commands.loggedin.delete import DeleteCommand
        from atheriz.globals.get import get_node_handler
        from atheriz.globals.objects import _ALL_OBJECTS
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord, strip_ansi

        room = Node(coord=Coord("privgatetest", 0, 0, 0))
        get_node_handler().add_node(room)
        caller = Object.create(None, "GateCaller")
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.msg = MagicMock()
        caller.location = room
        equal_victim = Object.create(None, "GateEqualVictim")
        equal_victim.privilege_level = settings.Privilege.Builder
        equal_victim.move_to(room)
        higher_victim = Object.create(None, "GateHigherVictim")
        higher_victim.privilege_level = settings.Privilege.Admin
        higher_victim.move_to(room)

        cmd = DeleteCommand()
        cmd.run(caller, cmd.parser.parse_args(["GateEqualVictim"]))
        cmd.run(caller, cmd.parser.parse_args(["GateHigherVictim"]))

        texts = [strip_ansi(str(a[0])) for a, _ in caller.msg.call_args_list]
        assert any(
            "equal or higher" in t or "permission" in t.lower() or "cannot delete" in t.lower()
            for t in texts
        ), f"expected privilege refusal, got {texts!r}"
        assert equal_victim.id in _ALL_OBJECTS, "equal-privilege target must survive refused delete"
        assert higher_victim.id in _ALL_OBJECTS, "higher-privilege target must survive refused delete"

    def test_builder_can_delete_lower_privilege_object(self, global_test_env):
        """The gate must only block equal-or-higher privilege, not all deletes."""
        from unittest.mock import MagicMock

        from atheriz.commands.loggedin.delete import DeleteCommand
        from atheriz.globals.get import get_node_handler
        from atheriz.globals.objects import _ALL_OBJECTS
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord, strip_ansi

        room = Node(coord=Coord("privgatetest", 0, 0, 0))
        get_node_handler().add_node(room)
        caller = Object.create(None, "GateCaller2")
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.msg = MagicMock()
        caller.location = room
        junior = Object.create(None, "GateJuniorVictim")
        junior.privilege_level = settings.Privilege.Player
        junior.move_to(room)

        cmd = DeleteCommand()
        cmd.run(caller, cmd.parser.parse_args(["GateJuniorVictim"]))

        texts = [strip_ansi(str(a[0])) for a, _ in caller.msg.call_args_list]
        assert any("Deleted" in t for t in texts), f"expected success, got {texts!r}"
        assert junior.id not in _ALL_OBJECTS

    def test_builder_can_delete_self(self, global_test_env):
        """Self-delete is exempt from the privilege gate (mirrors set.py)."""
        from unittest.mock import MagicMock

        from atheriz.commands.loggedin.delete import DeleteCommand
        from atheriz.globals.get import get_node_handler
        from atheriz.globals.objects import _ALL_OBJECTS
        from atheriz.objects.nodes import Node
        from atheriz.utils import Coord, strip_ansi

        room = Node(coord=Coord("privgatetest", 0, 0, 0))
        get_node_handler().add_node(room)
        caller = Object.create(None, "GateSelfDeleter")
        caller.privilege_level = settings.Privilege.Builder
        caller.quelled = False
        caller.msg = MagicMock()
        caller.location = room

        cmd = DeleteCommand()
        cmd.run(caller, cmd.parser.parse_args(["GateSelfDeleter"]))

        texts = [strip_ansi(str(a[0])) for a, _ in caller.msg.call_args_list]
        assert not any("equal or higher" in t for t in texts), f"self-delete must not hit privilege gate, got {texts!r}"
