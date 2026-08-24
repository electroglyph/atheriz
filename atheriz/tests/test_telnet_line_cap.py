"""Issue tests: the telnet shell read input with `reader.readline()`, which
telnetlib3 never bounds — its `limit` only feeds transport flow control, the
readline accumulator grows without bound. A client streaming data without a
terminator grew server memory unboundedly (the websocket path enforces
WEBSOCKET_MAX_MESSAGE_SIZE; telnet had nothing).

INTENT: `read_capped_lines` bounds per-connection buffering to max_line,
drops overlong lines (yielding None at the terminator), and preserves
telnetlib3's readline semantics for normal input (CR, LF, CR LF, CR NUL).
"""
from __future__ import annotations

import asyncio

from atheriz.network.telnet import read_capped_lines


class _FakeReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        return self._chunks.pop(0) if self._chunks else ""


def _collect(chunks, max_line=32):
    async def run():
        return [line async for line in read_capped_lines(_FakeReader(chunks), max_line)]

    return asyncio.run(run())


class TestNormalLines:
    def test_lines_pass_through_without_terminators(self):
        assert _collect(["hello\r\n", "wor", "ld\n"]) == ["hello", "world"]

    def test_cr_nul_and_bare_cr_are_terminators(self):
        assert _collect(["a\r\x00b\n", "c\r"]) == ["a", "b", "c"]

    def test_partial_line_at_eof_is_yielded(self):
        assert _collect(["part"]) == ["part"]

    def test_empty_input_yields_nothing(self):
        assert _collect([""]) == []


class TestOverlongLines:
    def test_single_overlong_line_dropped(self):
        assert _collect(["x" * 40 + "\n", "ok\n"]) == [None, "ok"]

    def test_terminatorless_flood_stays_bounded_and_dropped(self):
        """INTENT: the failing case for readline() — many chunks with no
        terminator. Buffering must stay capped and the line must be dropped
        once the terminator arrives."""
        chunks = ["x" * 40, "y" * 40, "z" * 40, "\n", "ok\n"]
        assert _collect(chunks) == [None, "ok"]

    def test_max_line_boundary_is_kept(self):
        assert _collect(["x" * 32 + "\n"]) == ["x" * 32]
        assert _collect(["x" * 33 + "\n"]) == [None]

    def test_following_line_unaffected_by_drop(self):
        assert _collect(["A" * 50 + "\r\n", "fine\n"]) == [None, "fine"]
