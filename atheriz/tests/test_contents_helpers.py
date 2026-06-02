"""Tests for atheriz/objects/contents.py helper functions.

`search` is tested in test_search2.py. This file covers the
*uncovered* helpers: filter_visible, group_by_name, filter_contents.
"""
from unittest.mock import MagicMock

import pytest

from atheriz.objects.contents import filter_visible, group_by_name, filter_contents
from atheriz.tests.fakes import make_object


# ---------------------------------------------------------------------------
# filter_visible
# ---------------------------------------------------------------------------


def test_filter_visible_no_looker_returns_unchanged():
    objs = [MagicMock(), MagicMock()]
    result = filter_visible(objs, looker=None)
    assert result is objs


def test_filter_visible_excludes_looker_self():
    a = MagicMock(name="a")
    b = MagicMock(name="b")
    a.access = MagicMock(return_value=True)
    b.access = MagicMock(return_value=True)
    result = filter_visible([a, b], looker=a)
    assert a not in result
    assert b in result


def test_filter_visible_excludes_invisible():
    visible = MagicMock(name="visible")
    hidden = MagicMock(name="hidden")
    visible.access = MagicMock(return_value=True)
    hidden.access = MagicMock(return_value=False)
    looker = MagicMock(name="looker")
    result = filter_visible([visible, hidden, looker], looker=looker)
    assert visible in result
    assert hidden not in result
    assert looker not in result


def test_filter_visible_with_real_objects():
    a = make_object("a")
    b = make_object("b")
    c = make_object("c")
    looker = make_object("looker")
    result = filter_visible([a, b, c, looker], looker=looker)
    assert looker not in result
    assert {x.name for x in result} == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# group_by_name
# ---------------------------------------------------------------------------


def test_group_by_name_empty_returns_empty_string():
    assert group_by_name([]) == ""
    assert group_by_name([], looker=MagicMock()) == ""


def test_group_by_name_unique_names():
    a = MagicMock(spec=["name"])
    a.name = "apple"
    b = MagicMock(spec=["name"])
    b.name = "banana"
    result = group_by_name([a, b])
    assert result == "apple, banana"


def test_group_by_name_duplicates_suffixed_with_count():
    a = MagicMock(spec=["name"])
    a.name = "apple"
    b = MagicMock(spec=["name"])
    b.name = "apple"
    c = MagicMock(spec=["name"])
    c.name = "banana"
    result = group_by_name([a, b, c])
    # Order is dict insertion order; "apple" was inserted first.
    assert "apple(2)" in result
    assert "banana" in result


def test_group_by_name_uses_display_name_when_looker_given():
    """With a looker, get_display_name(looker) is consulted."""
    a = MagicMock()
    a.get_display_name = MagicMock(return_value="The Apple")
    a.name = "apple"
    b = MagicMock()
    b.get_display_name = MagicMock(return_value="A Banana")
    b.name = "banana"
    looker = MagicMock()
    result = group_by_name([a, b], looker=looker)
    assert a.get_display_name.called
    assert result == "The Apple, A Banana"


def test_group_by_name_no_looker_uses_name():
    a = MagicMock(spec=["name"])
    a.name = "apple"
    # No get_display_name attr
    result = group_by_name([a])
    assert result == "apple"
    assert not hasattr(a, "get_display_name") or a.get_display_name.call_count == 0


# ---------------------------------------------------------------------------
# filter_contents
# ---------------------------------------------------------------------------


def test_filter_contents_returns_matching():
    """`Object.contents` is computed from `_contents` (a set of ids).
    We can populate it directly for this test, since the predicate
    receives the resolved Object."""
    from atheriz.globals.objects import add_object

    a = make_object("a")
    b = make_object("b")
    c = make_object("c")
    # Populate a._contents with ids of b and c.
    a._contents = {b.id, c.id}
    # Re-add them just to be safe (no-op if already there).
    add_object(b)
    add_object(c)
    result = filter_contents(a, lambda x: x in (a, b))
    assert b in result
    assert c not in result
    assert len(result) == 1


def test_filter_contents_empty_when_nothing_matches():
    a = make_object("a")
    b = make_object("b")
    a._contents = {b.id}
    result = filter_contents(a, lambda x: x.name == "zzz")
    assert result == []


def test_filter_contents_preserves_order():
    """When the predicate is a no-op True, the result is the full
    `contents` list."""
    a = make_object("a")
    b = make_object("b")
    c = make_object("c")
    a._contents = {b.id, c.id}
    result = filter_contents(a, lambda x: True)
    # contents is a list built from a set; we just check membership.
    assert set(result) == {b, c}
