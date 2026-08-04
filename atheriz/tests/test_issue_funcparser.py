"""Issue tests: `$eval`/`$py` arithmetic evaluation allows unbounded `**`
exponentiation (e.g. `$eval(9**9**9)`), a CPU/memory DoS vector.
"""
from __future__ import annotations

import pytest

from atheriz.objects.funcparser_helpers import _safe_arith_eval


class TestEvalExponentGuard:
    def test_large_exponent_is_rejected(self, global_test_env):
        """INTENT: exponentiation whose exponent value exceeds a sane cap must
        be rejected instead of being computed. `2**2**16` would raise under a
        guarded implementation; today it silently computes a ~20k-digit int."""
        with pytest.raises((ValueError, OverflowError)):
            _safe_arith_eval("2**2**16")

    def test_pow_guard_constant_is_defined(self, global_test_env):
        """INTENT: the safe-arithmetic module must define a maximum exponent
        constant that bounds `**` evaluation (protecting against expressions
        like `9**9**9`, which would otherwise hang the server)."""
        from atheriz.objects import funcparser_helpers as fh

        guard = getattr(fh, "_MAX_POW_EXPONENT", None)
        assert guard is not None
        assert guard < 9**9
