"""Issue tests: `$space`/`$pad`/`$just` accept unbounded width arguments,
letting a player trigger huge string allocations (memory DoS). The callables
live in `ACTOR_STANCE_CALLABLES`, merged into the parser used by
`msg_contents`.
"""
from __future__ import annotations

import pytest

from atheriz.objects.funcparser import ACTOR_STANCE_CALLABLES, FuncParser


class TestTextWidthGuard:
    def test_max_text_width_constant_is_defined(self, global_test_env):
        """INTENT: the text-width helper module must define a cap that bounds
        `$space`/`$pad`/`$just` allocations."""
        from atheriz.objects import funcparser_helpers as fh

        cap = getattr(fh, "_MAX_TEXT_WIDTH", None)
        assert cap is not None

    @pytest.mark.parametrize(
        "expr",
        [
            "$space(1000000000000)",
            "$pad(x, 1000000000000)",
            "$just(ab, align=l, width=1000000000000)",
        ],
    )
    def test_huge_width_is_bounded(self, global_test_env, expr):
        """INTENT: a player-requested width far beyond any screen must not
        allocate an enormous string."""
        from atheriz.objects import funcparser_helpers as fh

        parser = FuncParser(ACTOR_STANCE_CALLABLES)
        out = parser.parse(expr)
        assert isinstance(out, str)
        assert len(out) <= fh._MAX_TEXT_WIDTH
