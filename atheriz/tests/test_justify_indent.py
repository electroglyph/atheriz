"""Issue tests: `justify()`/`$just` accept an unbounded `indent` argument.

The callable clamped `width` but passed `indent` through unclamped, and
justify() multiplies it out (`sp * indent`) prepended to every output line —
so `$just(hi, indent=100000000)` in plain player text (say/emote via the
msg_contents parser) attempts a ~100 MB-per-line allocation. The fix clamps
indent to [0, width] at both layers.
"""

from __future__ import annotations

import pytest

from atheriz.objects.funcparser import ACTOR_STANCE_CALLABLES, FuncParser
from atheriz.objects.funcparser import funcparser_callable_justify
from atheriz.objects.funcparser_helpers import justify


class TestJustifyIndentGuard:
    def test_direct_unit_huge_indent_is_bounded(self, global_test_env):
        """INTENT: justify() itself must clamp indent; a huge value must not
        allocate (the buggy version would attempt ~1 GB per line)."""
        out = justify("hi", width=40, align="l", indent=10**9)
        assert isinstance(out, str)
        assert len(out) < 100

    def test_callable_kwargs_huge_indent(self, global_test_env):
        out = funcparser_callable_justify("hi", indent=10**9)
        assert all(len(line) <= 80 for line in out.split("\n"))

    def test_callable_positional_huge_indent(self, global_test_env):
        out = funcparser_callable_justify("hi", 40, "f", 10**9)
        assert all(len(line) <= 80 for line in out.split("\n"))

    def test_negative_indent_matches_zero(self, global_test_env):
        neg = justify("hi there friend", width=20, align="l", indent=-5)
        zero = justify("hi there friend", width=20, align="l", indent=0)
        assert neg == zero

    def test_reasonable_indent_still_applied(self, global_test_env):
        """INTENT: the clamp must not break legitimate small indents."""
        out = justify("hi", width=40, align="l", indent=4)
        first_line = out.split("\n")[0]
        assert first_line.startswith("    ")
        assert "hi" in first_line

    def test_parser_path_huge_indent_bounded(self, global_test_env):
        parser = FuncParser(ACTOR_STANCE_CALLABLES)
        out = parser.parse("$just(hi, indent=100000000)")
        assert isinstance(out, str)
        assert len(out) < 200


class TestJustifyIndentEndToEnd:
    def test_player_text_via_msg_contents_is_bounded(self, global_test_env):
        """INTENT: the full say/emote broadcast path (msg_contents with the
        actor-stance parser) must survive a player-supplied huge indent
        without MemoryError or unbounded output."""
        from unittest.mock import MagicMock

        from atheriz.objects.nodes import Node
        from atheriz.objects.base_obj import Object
        from atheriz.utils import Coord
        from atheriz.globals.objects import add_object

        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)

        alice = Object.create(None, "Alice")
        bob = Object.create(None, "Bob")
        bob.msg = MagicMock()
        bob.location = node
        node.add_object(alice)
        node.add_object(bob)

        node.msg_contents("Alice says: $just(hi, indent=100000000)")

        call = bob.msg.call_args_list[0]
        sent = call.args[0] if call.args else call.kwargs.get("text", "")
        assert len(sent) < 4096
