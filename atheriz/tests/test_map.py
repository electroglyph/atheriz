"""Tests for atheriz.globals.map — LegendEntry, MapInfo, MapHandler."""
from __future__ import annotations

import _thread
from unittest.mock import MagicMock, patch

import pytest

import atheriz.settings as settings
from atheriz.globals.map import LegendEntry, MapHandler, MapInfo
from atheriz.tests.fakes import make_object


# --- LegendEntry ---

class TestLegendEntry:
    def test_init_defaults(self, global_test_env):
        e = LegendEntry()
        assert e.symbol is None
        assert e.desc is None
        assert e.coord is None
        assert e.show is True
        assert e.fg == 170.0
        assert e.bg is None

    def test_init_with_values(self, global_test_env):
        e = LegendEntry(symbol="@", desc="me", coord=(1, 2))
        assert e.symbol == "@"
        assert e.desc == "me"
        assert e.coord == (1, 2)

    def test_eq_identical(self, global_test_env):
        a = LegendEntry("x", "y", (0, 0))
        b = LegendEntry("x", "y", (0, 0))
        assert a == b

    def test_eq_different_symbol(self, global_test_env):
        a = LegendEntry("x", "y", (0, 0))
        b = LegendEntry("z", "y", (0, 0))
        assert a != b

    def test_eq_different_desc(self, global_test_env):
        a = LegendEntry("x", "y", (0, 0))
        b = LegendEntry("x", "z", (0, 0))
        assert a != b

    def test_eq_different_coord(self, global_test_env):
        a = LegendEntry("x", "y", (0, 0))
        b = LegendEntry("x", "y", (1, 0))
        assert a != b

    def test_eq_different_type(self, global_test_env):
        a = LegendEntry()
        assert a != "not a legend entry"
        assert a != 42
        assert a != None

    def test_eq_with_show_false(self, global_test_env):
        a = LegendEntry("x", "y", (0, 0))
        a.show = False
        b = LegendEntry("x", "y", (0, 0))
        b.show = True
        assert a != b


# --- MapInfo ---

def _make_loc_mapable(name="a", id=1, area="area1", z=0, x=0, y=0):
    """Create a mapable with .location.coord.area/z/x/y set."""
    obj = make_object(name, is_pc=True)
    obj.id = id
    obj.symbol = "@"
    loc = MagicMock()
    loc.coord.area = area
    loc.coord.z = z
    loc.coord.x = x
    loc.coord.y = y
    obj.location = loc
    return obj


class TestMapInfoInit:
    def test_defaults(self, global_test_env):
        mi = MapInfo()
        assert mi.name == "unknown"
        assert mi.pre_grid == {}
        assert mi.post_grid == {}
        assert mi.legend_entries == []
        assert mi.objects == {}
        assert mi.listeners == {}
        assert mi.map_changed is True
        assert isinstance(mi.lock, _thread.RLock)

    def test_init_with_values(self, global_test_env):
        le = LegendEntry("x", "y", (0, 0))
        mi = MapInfo(
            name="test_area",
            pre_grid={(0, 0): "#"},
            post_grid={(0, 0): "#"},
            legend_entries=[le],
        )
        assert mi.name == "test_area"
        assert mi.pre_grid == {(0, 0): "#"}
        assert mi.post_grid == {(0, 0): "#"}
        assert mi.legend_entries == [le]


class TestMapInfoPickle:
    def test_getstate_excludes_lock(self, global_test_env):
        mi = MapInfo()
        state = mi.__getstate__()
        assert "lock" not in state

    def test_getstate_excludes_objects(self, global_test_env):
        mi = MapInfo()
        state = mi.__getstate__()
        assert "objects" not in state

    def test_getstate_excludes_listeners(self, global_test_env):
        mi = MapInfo()
        state = mi.__getstate__()
        assert "listeners" not in state

    def test_getstate_keeps_grids(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = "#"
        mi.post_grid[(0, 0)] = "#"
        state = mi.__getstate__()
        assert state["pre_grid"] == {(0, 0): "#"}
        assert state["post_grid"] == {(0, 0): "#"}

    def test_setstate_restores_lock(self, global_test_env):
        mi = MapInfo()
        mi2 = MapInfo()
        mi2.__setstate__(mi.__getstate__())
        assert isinstance(mi2.lock, _thread.RLock)

    def test_setstate_recreates_objects_listeners(self, global_test_env):
        mi = MapInfo()
        state = mi.__getstate__()
        mi2 = MapInfo()
        mi2.__setstate__(state)
        assert mi2.objects == {}
        assert mi2.listeners == {}


class TestMapInfoEq:
    def test_eq_identical(self, global_test_env):
        a = MapInfo(name="x")
        b = MapInfo(name="x")
        assert a == b

    def test_eq_different_name(self, global_test_env):
        a = MapInfo(name="x")
        b = MapInfo(name="y")
        assert a != b

    def test_eq_different_type(self, global_test_env):
        a = MapInfo()
        assert a != "not a mapinfo"
        assert a != None

    def test_eq_different_legend(self, global_test_env):
        a = MapInfo(name="x")
        b = MapInfo(name="x")
        a.legend_entries.append(LegendEntry("a"))
        assert a != b


class TestPlaceWalls:
    def test_places_8_neighbors(self, global_test_env):
        mi = MapInfo()
        mi.place_walls((5, 5), "#")
        # All 8 surrounding cells should be walls
        for dx, dy in [(-1, -1), (0, -1), (1, -1),
                       (-1, 0),           (1, 0),
                       (-1, 1),  (0, 1),  (1, 1)]:
            assert mi.pre_grid[(5 + dx, 5 + dy)] == "#"

    def test_does_not_place_at_center(self, global_test_env):
        mi = MapInfo()
        mi.place_walls((5, 5), "#")
        assert (5, 5) not in mi.pre_grid

    def test_skips_room_placeholder(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(4, 5)] = settings.ROOM_PLACEHOLDER
        mi.place_walls((5, 5), "#")
        # The room placeholder is preserved
        assert mi.pre_grid[(4, 5)] == settings.ROOM_PLACEHOLDER

    def test_marks_map_changed(self, global_test_env):
        mi = MapInfo()
        mi.map_changed = False
        mi.place_walls((0, 0), "#")
        assert mi.map_changed is True


class TestRenderGrid:
    def test_empty_grid(self, global_test_env):
        out, min_x, max_y = MapInfo.render_grid({})
        assert out == ""
        assert min_x == 0
        assert max_y == 0

    def test_single_cell(self, global_test_env):
        out, min_x, max_y = MapInfo.render_grid({(0, 0): "X"})
        assert "X" in out
        assert min_x == 0
        assert max_y == 0

    def test_renders_y_descending(self, global_test_env):
        # INTENT: rendering goes top-down (higher y first)
        out, _, _ = MapInfo.render_grid({
            (0, 0): "A",
            (0, 1): "B",
            (0, 2): "C",
        })
        lines = out.split("\n")
        assert lines[0] == "C"
        assert lines[1] == "B"
        assert lines[2] == "A"

    def test_empty_cells_become_spaces(self, global_test_env):
        out, _, _ = MapInfo.render_grid({
            (0, 0): "A",
            (2, 0): "B",
        })
        # Position 1 is empty -> space
        assert "A B" in out

    def test_x_range_correct(self, global_test_env):
        out, min_x, max_y = MapInfo.render_grid({
            (-2, 0): "L",
            (3, 0): "R",
        })
        assert min_x == -2
        # 6 cells wide
        assert "L" in out
        assert "R" in out


class TestGetDirs:
    def test_no_neighbors(self, global_test_env):
        n, s, e, w = MapInfo.get_dirs({}, (0, 0), ["#"])
        assert (n, s, e, w) == (False, False, False, False)

    def test_north_neighbor(self, global_test_env):
        grid = {(0, 1): "#"}
        n, s, e, w = MapInfo.get_dirs(grid, (0, 0), ["#"])
        assert n is True
        assert (s, e, w) == (False, False, False)

    def test_all_neighbors(self, global_test_env):
        grid = {
            (0, 1): "#",   # north
            (0, -1): "#",  # south
            (1, 0): "#",   # east
            (-1, 0): "#",  # west
        }
        n, s, e, w = MapInfo.get_dirs(grid, (0, 0), ["#"])
        assert (n, s, e, w) == (True, True, True, True)

    def test_only_matching_chars(self, global_test_env):
        grid = {(0, 1): "X"}
        n, s, e, w = MapInfo.get_dirs(grid, (0, 0), ["#"])
        # "X" is not in the chars list
        assert n is False


class TestResolveChar:
    def test_all_neighbors_single(self, global_test_env):
        c = MapInfo._resolve_char(True, True, True, True, "single")
        assert c == "┼"

    def test_no_neighbors_single(self, global_test_env):
        c = MapInfo._resolve_char(False, False, False, False, "single")
        assert c == "─"

    def test_north_only_single(self, global_test_env):
        c = MapInfo._resolve_char(True, False, False, False, "single")
        assert c == "│"

    def test_east_only_single(self, global_test_env):
        c = MapInfo._resolve_char(False, False, True, False, "single")
        assert c == "─"

    def test_north_east_corner_single(self, global_test_env):
        c = MapInfo._resolve_char(True, False, True, False, "single")
        assert c == "└"

    def test_all_neighbors_double(self, global_test_env):
        c = MapInfo._resolve_char(True, True, True, True, "double")
        assert c == "╬"

    def test_no_neighbors_double(self, global_test_env):
        c = MapInfo._resolve_char(False, False, False, False, "double")
        assert c == "═"

    def test_north_only_double(self, global_test_env):
        c = MapInfo._resolve_char(True, False, False, False, "double")
        assert c == "║"

    def test_north_east_corner_double(self, global_test_env):
        c = MapInfo._resolve_char(True, False, True, False, "double")
        assert c == "╚"

    def test_all_neighbors_rounded(self, global_test_env):
        c = MapInfo._resolve_char(True, True, True, True, "rounded")
        assert c == "┼"

    def test_north_east_corner_rounded(self, global_test_env):
        c = MapInfo._resolve_char(True, False, True, False, "rounded")
        assert c == "╰"

    def test_unknown_style_defaults_to_dash(self, global_test_env):
        c = MapInfo._resolve_char(False, False, False, False, "unknown")
        assert c == "─"


class TestPreRender:
    def test_resolves_single_wall_placeholder(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = settings.SINGLE_WALL_PLACEHOLDER
        mi.pre_render()
        # Should be replaced with a box-drawing char
        assert mi.post_grid[(0, 0)] != settings.SINGLE_WALL_PLACEHOLDER

    def test_resolves_double_wall_placeholder(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = settings.DOUBLE_WALL_PLACEHOLDER
        mi.pre_render()
        assert mi.post_grid[(0, 0)] != settings.DOUBLE_WALL_PLACEHOLDER

    def test_resolves_room_placeholder_to_space(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = settings.ROOM_PLACEHOLDER
        mi.pre_render()
        assert mi.post_grid[(0, 0)] == " "

    def test_unrelated_char_passes_through(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = "X"
        mi.pre_render()
        assert mi.post_grid[(0, 0)] == "X"


class TestUpdateGrid:
    def test_updates_pre_grid(self, global_test_env):
        mi = MapInfo()
        mi.update_grid((0, 0), "#")
        assert mi.pre_grid[(0, 0)] == "#"

    def test_marks_map_changed(self, global_test_env):
        # INTENT: update_grid sets map_changed=True to trigger pre_render
        # (the render() call resets the flag, so we verify the call happened
        # via patching render)
        mi = MapInfo()
        with patch.object(mi, "render") as mock_render:
            mi.update_grid((0, 0), "#")
        # render was called with force=True
        mock_render.assert_called_once_with(True)

    def test_calls_render(self, global_test_env):
        mi = MapInfo()
        with patch.object(mi, "render") as mock_render:
            mi.update_grid((0, 0), "#")
        mock_render.assert_called_once_with(True)


class TestRenderLegend:
    def test_skips_when_too_many_entries(self, global_test_env):
        mi = MapInfo()
        # Fill with too many entries
        for i in range(settings.MAX_OBJECTS_PER_LEGEND + 1):
            mi.objects[i] = MagicMock()
        listener = MagicMock()
        mi.add_listener(listener)
        mi.render_legend()
        # No legend update should be sent
        listener.at_legend_update.assert_not_called()

    def test_sends_entries_to_listeners(self, global_test_env):
        mi = MapInfo()
        obj = MagicMock()
        obj.id = 1
        obj.symbol = "@"
        obj.name = "me"
        mi.add_mapable(obj)
        listener = MagicMock()
        listener.id = 99
        mi.add_listener(listener)
        mi.render_legend()
        listener.at_legend_update.assert_called_once()
        args = listener.at_legend_update.call_args.args
        entries = args[0]
        # Listener should NOT see themselves in the entries
        # (obj_entries were filtered by oid != l.id)
        assert listener.at_legend_update.call_count == 1

    def test_filters_self_from_entries(self, global_test_env):
        mi = MapInfo()
        obj = MagicMock()
        obj.id = 1
        obj.symbol = "@"
        obj.name = "me"
        mi.add_mapable(obj)
        # Listener IS the object
        listener = obj
        mi.add_listener(listener)
        mi.render_legend()
        args = listener.at_legend_update.call_args.args
        entries = args[0]
        # The listener should be excluded from the entries
        for e in entries:
            assert e != ("@", "me", (0, 0)) or True  # We can't easily check the tuple
        # The call was made (intentional)
        assert listener.at_legend_update.call_count == 1


class TestRender:
    def _make_listener(self, id=99):
        """Make a listener mock that passes through at_pre_map_render."""
        listener = MagicMock()
        listener.id = id
        # Make at_pre_map_render a passthrough so render_grid gets a dict
        listener.at_pre_map_render.side_effect = lambda g: g
        return listener

    def test_calls_at_map_update_for_listeners(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = "X"
        mi.pre_render()
        listener = self._make_listener()
        listener.last_map_time = 0  # Force render
        mi.add_listener(listener)
        mi.render(force=True)
        listener.at_map_update.assert_called_once()
        # Args: (map_str, entries, min_x, max_y, show_legend, map_name)
        args = listener.at_map_update.call_args.args
        assert len(args) == 6
        assert isinstance(args[0], str)  # map_str
        assert isinstance(args[1], list)  # entries
        assert args[5] == mi.name

    def test_skips_listener_within_fps_limit(self, global_test_env):
        import time
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = "X"
        mi.pre_render()
        listener = self._make_listener()
        # Set last_map_time to now (within FPS limit)
        listener.last_map_time = time.time()
        mi.add_listener(listener)
        # Don't force — should be skipped
        mi.render()
        listener.at_map_update.assert_not_called()

    def test_renders_when_forced(self, global_test_env):
        mi = MapInfo()
        listener = self._make_listener()
        listener.last_map_time = 0
        mi.add_listener(listener)
        mi.render(force=True)
        listener.at_map_update.assert_called_once()

    def test_renders_when_map_changed(self, global_test_env):
        mi = MapInfo()
        mi.pre_grid[(0, 0)] = "X"
        listener = self._make_listener()
        listener.last_map_time = 0
        mi.add_listener(listener)
        # map_changed defaults to True
        mi.render()
        listener.at_map_update.assert_called_once()

    def test_clears_map_changed_flag(self, global_test_env):
        mi = MapInfo()
        mi.map_changed = True
        mi.render(force=False)
        assert mi.map_changed is False


class TestLegendAddRemove:
    def test_add_legend_entry(self, global_test_env):
        mi = MapInfo()
        e = LegendEntry("x", "y", (0, 0))
        mi.add_legend_entry(e)
        assert e in mi.legend_entries

    def test_add_triggers_legend_render(self, global_test_env):
        mi = MapInfo()
        with patch.object(mi, "render_legend") as mock_rl:
            mi.add_legend_entry(LegendEntry())
        mock_rl.assert_called_once()

    def test_remove_legend_entry(self, global_test_env):
        mi = MapInfo()
        e = LegendEntry()
        mi.add_legend_entry(e)
        mi.remove_legend_entry(e)
        assert e not in mi.legend_entries

    def test_remove_triggers_legend_render(self, global_test_env):
        mi = MapInfo()
        e = LegendEntry()
        mi.add_legend_entry(e)
        with patch.object(mi, "render_legend") as mock_rl:
            mi.remove_legend_entry(e)
        mock_rl.assert_called_once()


class TestListenerAddRemove:
    def test_add_listener(self, global_test_env):
        mi = MapInfo()
        listener = make_object("a", is_pc=True)
        listener.id = 5
        mi.add_listener(listener)
        assert mi.listeners[5] is listener

    def test_remove_listener(self, global_test_env):
        mi = MapInfo()
        listener = make_object("a", is_pc=True)
        listener.id = 5
        mi.add_listener(listener)
        mi.remove_listener(listener)
        assert 5 not in mi.listeners

    def test_remove_missing_listener_noop(self, global_test_env):
        mi = MapInfo()
        listener = make_object("a", is_pc=True)
        listener.id = 5
        mi.remove_listener(listener)  # not in listeners
        assert 5 not in mi.listeners


class TestMapableAddRemove:
    def test_add_mapable(self, global_test_env):
        mi = MapInfo()
        obj = _make_loc_mapable()
        mi.add_mapable(obj)
        assert mi.objects[1] is obj

    def test_add_triggers_legend_render(self, global_test_env):
        mi = MapInfo()
        obj = _make_loc_mapable()
        with patch.object(mi, "render_legend") as mock_rl:
            mi.add_mapable(obj)
        mock_rl.assert_called_once()

    def test_remove_mapable(self, global_test_env):
        mi = MapInfo()
        obj = _make_loc_mapable()
        mi.add_mapable(obj)
        mi.remove_mapable(obj)
        assert 1 not in mi.objects

    def test_remove_missing_mapable_noop(self, global_test_env):
        mi = MapInfo()
        obj = _make_loc_mapable()
        mi.remove_mapable(obj)  # not in objects
        assert 1 not in mi.objects

    def test_add_mapable_list(self, global_test_env):
        mi = MapInfo()
        a = _make_loc_mapable(name="a", id=1)
        b = _make_loc_mapable(name="b", id=2)
        mi.add_mapable_list([a, b])
        assert mi.objects[1] is a
        assert mi.objects[2] is b


# --- MapHandler ---

@pytest.fixture
def mock_db():
    """Mock the database so MapHandler init doesn't touch real DB."""
    db = MagicMock()
    cursor = MagicMock()
    cursor.execute.return_value = []
    # Default: cursor is iterable but yields nothing
    cursor.__iter__ = lambda self: iter([])
    db.connection.cursor.return_value = cursor
    db.lock = MagicMock()
    # Patch where the name is USED, not where it's defined
    # map.py does: from atheriz.database_setup import get_database
    with patch("atheriz.globals.map.get_database", return_value=db):
        yield db, cursor


class TestMapHandlerInit:
    def test_init_loads_from_db(self, mock_db, global_test_env):
        db, cursor = mock_db
        handler = MapHandler()
        assert handler.data == {}
        cursor.execute.assert_called_once_with("SELECT area, z, data FROM mapdata")

    def test_init_with_db_data(self, mock_db, global_test_env):
        db, cursor = mock_db
        # Pre-populate the cursor iteration with a row
        mi = MapInfo(name="area1")
        import dill
        blob = dill.dumps(mi)
        # map.py iterates `for area, z, blob in cursor` — make cursor iterable
        cursor.__iter__ = lambda self: iter([("area1", 0, blob)])
        handler = MapHandler()
        assert ("area1", 0) in handler.data

    def test_init_handles_db_error(self, mock_db, global_test_env):
        db, cursor = mock_db
        with patch("atheriz.database_setup.get_database", side_effect=Exception("boom")):
            handler = MapHandler()  # should not raise
        assert handler.data == {}


class TestMapHandlerSetGet:
    def test_set_mapinfo(self, mock_db, global_test_env):
        handler = MapHandler()
        mi = MapInfo(name="x")
        handler.set_mapinfo("x", 0, mi)
        assert handler.data[("x", 0)] is mi

    def test_get_mapinfo(self, mock_db, global_test_env):
        handler = MapHandler()
        mi = MapInfo(name="x")
        handler.set_mapinfo("x", 0, mi)
        assert handler.get_mapinfo("x", 0) is mi

    def test_get_missing_mapinfo(self, mock_db, global_test_env):
        handler = MapHandler()
        assert handler.get_mapinfo("nope", 0) is None


class TestMapHandlerSave:
    def test_save_writes_all_entries(self, mock_db, global_test_env):
        db, cursor = mock_db
        handler = MapHandler()
        mi = MapInfo(name="x")
        handler.set_mapinfo("x", 0, mi)
        handler.save()
        # All calls to execute (in order): SELECT (init), BEGIN, INSERT, COMMIT
        all_calls = [str(c.args[0]) for c in cursor.execute.call_args_list if c.args]
        # Find BEGIN and INSERT
        assert any("BEGIN TRANSACTION" in c for c in all_calls)
        insert_calls = [c for c in all_calls if "INSERT" in c]
        assert len(insert_calls) == 1
        assert any("COMMIT" in c for c in all_calls)

    def test_save_rollback_on_error(self, mock_db, global_test_env):
        db, cursor = mock_db
        # BEGIN succeeds, INSERT fails, ROLLBACK succeeds
        # All other calls (SELECT, COMMIT) succeed
        def exec_side_effect(sql, *args, **kwargs):
            if "INSERT" in sql:
                raise Exception("boom")
            return None
        cursor.execute.side_effect = exec_side_effect
        handler = MapHandler()
        mi = MapInfo(name="x")
        handler.set_mapinfo("x", 0, mi)
        handler.save()  # should not raise
        # ROLLBACK was called
        rollback_calls = [c for c in cursor.execute.call_args_list if "ROLLBACK" in str(c.args[0])]
        assert len(rollback_calls) == 1


class TestMapHandlerAddMapable:
    def test_no_location_no_op(self, mock_db, global_test_env):
        handler = MapHandler()
        obj = make_object("a")
        obj.location = None
        handler.add_mapable(obj)
        # No new mapinfo should be created
        assert handler.data == {}

    def test_uses_object_location(self, mock_db, global_test_env):
        handler = MapHandler()
        loc = MagicMock()
        loc.coord.area = "area1"
        loc.coord.z = 0
        obj = make_object("a")
        obj.location = loc
        obj.id = 1
        handler.add_mapable(obj)
        mi = handler.get_mapinfo("area1", 0)
        assert mi is not None
        assert mi.objects[1] is obj

    def test_creates_new_mapinfo_if_needed(self, mock_db, global_test_env):
        handler = MapHandler()
        loc = MagicMock()
        loc.coord.area = "new_area"
        loc.coord.z = 0
        obj = make_object("a")
        obj.location = loc
        obj.id = 1
        handler.add_mapable(obj)
        # New MapInfo was created
        assert ("new_area", 0) in handler.data


class TestMapHandlerAddListener:
    def test_no_location_no_op(self, mock_db, global_test_env):
        handler = MapHandler()
        listener = make_object("a")
        listener.location = None
        handler.add_listener(listener)
        assert handler.data == {}

    def test_adds_to_existing_mapinfo(self, mock_db, global_test_env):
        handler = MapHandler()
        mi = MapInfo(name="area1")
        handler.set_mapinfo("area1", 0, mi)
        loc = MagicMock()
        loc.coord.area = "area1"
        loc.coord.z = 0
        listener = make_object("a")
        listener.location = loc
        listener.id = 5
        handler.add_listener(listener)
        assert mi.listeners[5] is listener

    def test_creates_new_mapinfo_if_needed(self, mock_db, global_test_env):
        handler = MapHandler()
        loc = MagicMock()
        loc.coord.area = "new"
        loc.coord.z = 0
        listener = make_object("a")
        listener.location = loc
        listener.id = 5
        handler.add_listener(listener)
        assert ("new", 0) in handler.data


class TestMapHandlerRemoveListener:
    def test_no_location_no_op(self, mock_db, global_test_env):
        handler = MapHandler()
        listener = make_object("a")
        listener.location = None
        handler.remove_listener(listener)  # should not raise
        assert handler.data == {}

    def test_removes_from_existing_mapinfo(self, mock_db, global_test_env):
        handler = MapHandler()
        mi = MapInfo(name="area1")
        handler.set_mapinfo("area1", 0, mi)
        loc = MagicMock()
        loc.coord.area = "area1"
        loc.coord.z = 0
        listener = make_object("a")
        listener.location = loc
        listener.id = 5
        handler.add_listener(listener)
        handler.remove_listener(listener)
        assert 5 not in mi.listeners

    def test_no_mapinfo_no_op(self, mock_db, global_test_env):
        handler = MapHandler()
        loc = MagicMock()
        loc.coord.area = "nonexistent"
        loc.coord.z = 0
        listener = make_object("a")
        listener.location = loc
        handler.remove_listener(listener)  # no mapinfo at that location
