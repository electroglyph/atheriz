"""Tests for atheriz.connection_screen — login banner rendering."""
from __future__ import annotations

from importlib import metadata as importlib_metadata

import pytest

import atheriz.connection_screen as cs
from atheriz.globals.objects import filter_by
from atheriz.tests.fakes import make_object


def _make_pc(name: str, connected: bool = False):
    obj = make_object(name, is_pc=True, is_connected=connected)
    return obj


def _make_npc(name: str):
    obj = make_object(name, is_pc=False, is_npc=True, is_connected=False)
    return obj


class TestGetOnline:
    def test_empty(self, global_test_env):
        assert cs.get_online() == (0, 0)

    def test_only_pcs(self, global_test_env):
        _make_pc("alice", connected=True)
        _make_pc("bob", connected=False)
        _make_pc("carol", connected=True)
        online, total = cs.get_online()
        assert online == 2
        assert total == 3

    def test_npcs_excluded(self, global_test_env):
        _make_pc("alice", connected=True)
        _make_npc("guard")
        _make_npc("shopkeeper")
        _make_npc("monster")
        online, total = cs.get_online()
        assert online == 1
        assert total == 1

    def test_no_connected(self, global_test_env):
        _make_pc("alice", connected=False)
        _make_pc("bob", connected=False)
        assert cs.get_online() == (0, 2)

    def test_all_connected(self, global_test_env):
        _make_pc("alice", connected=True)
        _make_pc("bob", connected=True)
        assert cs.get_online() == (2, 2)

    def test_mixed(self, global_test_env):
        _make_pc("a", connected=True)
        _make_pc("b", connected=False)
        _make_pc("c", connected=True)
        _make_pc("d", connected=False)
        _make_npc("x")
        assert cs.get_online() == (2, 4)

    def test_pcs_with_truthy_non_bool_connected(self, global_test_env):
        # The implementation sums truthy is_connected values
        _make_pc("a", connected=1)
        _make_pc("b", connected=0)
        online, total = cs.get_online()
        assert online == 1
        assert total == 2


class TestRender:
    def test_render_no_session(self, global_test_env):
        out = cs.render()
        assert isinstance(out, str)
        assert cs.SCREEN.split("\n")[0].strip() in out
        assert "ATHERIZ VERSION" in out
        assert "KNOWN ADVENTURERS = 0" in out
        assert "ONLINE ADVENTURERS = 0" in out
        assert "enter 'connect" in out
        assert "screenreader mode" in out

    def test_render_uses_screen_for_normal_session(self, global_test_env):
        class _S:
            screenreader = False
        s = _S()
        out = cs.render(s)
        # SCREEN has the ASCII art at the top
        assert "_____" in out
        assert "ATHERIZ VERSION" in out

    def test_render_uses_screen2_for_screenreader(self, global_test_env):
        class _S:
            screenreader = True
        s = _S()
        out = cs.render(s)
        # SCREEN2 has no ASCII art (the ATHERIZ VERSION line is the first content)
        assert "_____" not in out
        assert "ATHERIZ VERSION" in out
        assert "KNOWN ADVENTURERS = 0" in out
        assert "ONLINE ADVENTURERS = 0" in out

    def test_render_includes_version(self, global_test_env):
        out = cs.render()
        expected_version = importlib_metadata.version("atheriz")
        assert f"ATHERIZ VERSION = {expected_version}" in out

    def test_render_includes_counts(self, global_test_env):
        _make_pc("alice", connected=True)
        _make_pc("bob", connected=False)
        _make_npc("guard")
        out = cs.render()
        assert "KNOWN ADVENTURERS = 2" in out
        assert "ONLINE ADVENTURERS = 1" in out

    def test_render_screenreader_includes_counts(self, global_test_env):
        _make_pc("alice", connected=True)
        _make_pc("bob", connected=True)
        out = cs.render(_FakeSR())
        assert "KNOWN ADVENTURERS = 2" in out
        assert "ONLINE ADVENTURERS = 2" in out
        assert "_____" not in out

    def test_render_session_none_falls_through_to_screen(self, global_test_env):
        # session=None branch
        out = cs.render(None)
        assert "_____" in out


class TestModuleConstants:
    def test_guest_text_is_string(self):
        assert isinstance(cs.GUEST_TEXT, str)

    def test_screen_contains_placeholders(self):
        assert "{version}" in cs.SCREEN
        assert "{known}" in cs.SCREEN
        assert "{online}" in cs.SCREEN
        assert "{GUEST_TEXT}" in cs.SCREEN

    def test_screen2_contains_placeholders(self):
        assert "{version}" in cs.SCREEN2
        assert "{known}" in cs.SCREEN2
        assert "{online}" in cs.SCREEN2
        assert "{GUEST_TEXT}" in cs.SCREEN2

    def test_screen_is_larger_than_screen2(self):
        # The full ASCII-art SCREEN should be longer than the trimmed SCREEN2
        assert len(cs.SCREEN) > len(cs.SCREEN2)


class _FakeSR:
    screenreader = True
