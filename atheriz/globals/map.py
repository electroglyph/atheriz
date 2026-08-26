from __future__ import annotations
from threading import RLock
from contextlib import contextmanager
from atheriz.globals.node import Node
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.utils import Coord, detach, strip_ansi
import dill
import time
import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


# Maps each placeholder character to its box-drawing style.
# Used by pre_render for a single-pass placeholder resolution.
_PLACEHOLDER_STYLES: dict[str, str] = {
    settings.SINGLE_WALL_PLACEHOLDER: "single",
    settings.DOUBLE_WALL_PLACEHOLDER: "double",
    settings.ROUNDED_WALL_PLACEHOLDER: "rounded",
    settings.PATH_PLACEHOLDER: "rounded",
    settings.ROAD_PLACEHOLDER: "double",
}


class LegendEntry:
    """
    this is for adding information about environment symbols on the map.
    symbols will be placed on the map in first render pass
    """

    def __init__(
        self, symbol: str | None = None, desc: str | None = None, coord: tuple | None = None
    ) -> None:
        self.symbol: str = symbol
        self.desc: str = desc
        self.coord: tuple[int, int] = coord
        self.show = True  # whether to show this entry in the legend.  this will be False if it's grouped with another entry
        self.fg = 170.0
        self.bg = None

    def __eq__(self, other):
        if not isinstance(other, LegendEntry):
            return False
        return (
            self.symbol == other.symbol and
            self.desc == other.desc and
            self.coord == other.coord and
            self.show == other.show and
            self.fg == other.fg and
            self.bg == other.bg
        )

    # def __getstate__(self):
    #     d = self.__dict__.copy()
    #     d["coord"] = tuple_to_str(d["coord"])
    #     return d

    # def __setstate__(self, state):
    #     if state:
    #         self.__dict__.update(state)
    #         self.coord = str_to_tuple(state["coord"])


class MapInfo:
    def __init__(
        self,
        name: str = "unknown",
        pre_grid: dict[tuple[int, int], str] | None = None,
        post_grid: dict[tuple[int, int], str] | None = None,
        legend_entries: list[LegendEntry] | None = None,
    ) -> None:
        self.name = name
        self.map_changed = True
        # pre_grid holds wall, road, and path placeholders
        self.pre_grid: dict[tuple[int, int], str] = pre_grid if pre_grid else {}
        # post_grid is the grid after rendering the placeholders
        self.post_grid: dict[tuple[int, int], str] = post_grid if post_grid else {}
        self.legend_entries: list[LegendEntry] = legend_entries if legend_entries else []
        self.objects: dict[int, Object] = {}
        self.listeners: dict[int, Object] = {}
        self.lock = RLock()
        self._batch_update = 0
        self._legend_suppressed = False

    def _is_over_legend_cap(self) -> bool:
        return len(self.objects) + len(self.legend_entries) > settings.MAX_OBJECTS_PER_LEGEND
    
    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            state.pop("objects", None)
            state.pop("listeners", None)
            state.pop("_batch_update", None)
            state.pop("_legend_suppressed", None)
            return state
    
    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()
        self.objects: dict[int, Object] = {}
        self.listeners: dict[int, Object] = {}
        self._batch_update = 0
        self._legend_suppressed = False

    def __eq__(self, other):
        if not isinstance(other, MapInfo):
            return False
        return (
            self.name == other.name and
            self.pre_grid == other.pre_grid and
            self.post_grid == other.post_grid and
            self.legend_entries == other.legend_entries
        )

    def place_walls(self, coord: tuple[int, int], char: str):
        """
        places walls around a coordinate
        """
        with self.lock:
            cx, cy = coord
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    if dx == 0 and dy == 0:
                        continue
                    if self.pre_grid.get((cx + dx, cy + dy), None) == settings.ROOM_PLACEHOLDER:
                        continue
                    self.pre_grid[(cx + dx, cy + dy)] = char
            self.map_changed = True

    @staticmethod
    def render_grid(grid: dict[tuple[int, int], str]):
        """
        renders the grid into a string
        Returns: tuple of (rendered_string, min_x, max_y)
        """
        if not grid:
            logger.warning("render_grid called with empty grid")
            return "", 0, 0
        keys = grid.keys()
        min_x = min(k[0] for k in keys)
        max_x = max(k[0] for k in keys)
        min_y = min(k[1] for k in keys)
        max_y = max(k[1] for k in keys)
        lines = []
        for y in range(max_y, min_y - 1, -1):
            row_chars = []
            for x in range(min_x, max_x + 1):
                row_chars.append(grid.get((x, y), " "))
            lines.append("".join(row_chars))
        return "\n".join(lines), min_x, max_y

    @staticmethod
    def get_dirs(
        grid: dict[tuple[int, int], str], coord: tuple[int, int], chars: list[str]
    ) -> tuple[bool, bool, bool, bool]:
        """
        returns a tuple of booleans representing the directions of the walls around a coordinate
        """
        n = False
        s = False
        e = False
        w = False
        cx, cy = coord
        value = grid.get((cx, cy + 1), None)
        if value is not None and strip_ansi(value) in chars:
            n = True
        value = grid.get((cx, cy - 1), None)
        if value is not None and strip_ansi(value) in chars:
            s = True
        value = grid.get((cx + 1, cy), None)
        if value is not None and strip_ansi(value) in chars:
            e = True
        value = grid.get((cx - 1, cy), None)
        if value is not None and strip_ansi(value) in chars:
            w = True
        return n, s, e, w

    @staticmethod
    def _resolve_char(n: bool, s: bool, e: bool, w: bool, style: str) -> str:
        """
        Returns the box-drawing character for the given neighbor directions and wall style.
        Used by pre_render for single-pass placeholder resolution.
        """
        if style == "single":
            if n and s and e and w: return "┼"
            elif n and s and e: return "├"
            elif n and s and w: return "┤"
            elif n and e and w: return "┴"
            elif s and e and w: return "┬"
            elif n and e: return "└"
            elif n and w: return "┘"
            elif s and e: return "┌"
            elif s and w: return "┐"
            elif n and s: return "│"
            elif e and w: return "─"
            elif n or s: return "│"
            else: return "─"
        elif style == "double":
            if n and s and e and w: return "╬"
            elif n and s and e: return "╠"
            elif n and s and w: return "╣"
            elif n and e and w: return "╩"
            elif s and e and w: return "╦"
            elif n and e: return "╚"
            elif n and w: return "╝"
            elif s and e: return "╔"
            elif s and w: return "╗"
            elif n and s: return "║"
            elif e and w: return "═"
            elif n or s: return "║"
            else: return "═"
        elif style == "rounded":
            if n and s and e and w: return "┼"
            elif n and s and e: return "├"
            elif n and s and w: return "┤"
            elif n and e and w: return "┴"
            elif s and e and w: return "┬"
            elif n and e: return "╰"
            elif n and w: return "╯"
            elif s and e: return "╭"
            elif s and w: return "╮"
            elif n and s: return "│"
            elif e and w: return "─"
            elif n or s: return "│"
            else: return "─"
        return "─"

    def pre_render(self):
        """
        Resolves all placeholder characters to their final box-drawing glyphs
        in a single pass over the grid, then stores the result in post_grid.
        """
        with self.lock:
            rendered = copy.deepcopy(self.pre_grid)
            original = self.pre_grid.copy()
            to_place = {}
            for k, v in rendered.items():
                style = _PLACEHOLDER_STYLES.get(v)
                if style is not None:
                    n, s, e, w = MapInfo.get_dirs(original, k, settings.ALL_SYMBOLS)
                    to_place[k] = MapInfo._resolve_char(n, s, e, w, style)
                elif v == settings.ROOM_PLACEHOLDER:
                    to_place[k] = " "
            rendered.update(to_place)
            self.post_grid = rendered

    def update_grid(self, coord: tuple[int, int], new_symbol: str):
        with self.lock:
            self.pre_grid[coord] = new_symbol
            self.map_changed = True
            should_render = self._batch_update == 0
        if should_render:
            self.render(True)

    @contextmanager
    def batch_update(self):
        with self.lock:
            self._batch_update += 1
            # post_grid-only maps (e.g. generated buildings have no
            # placeholders) must be seeded into pre_grid before the first
            # edit, or the render on exit would replace post_grid with just
            # the edited cells and wipe everything untouched.
            if not self.pre_grid and self.post_grid:
                self.pre_grid = copy.deepcopy(self.post_grid)
        try:
            yield
        finally:
            with self.lock:
                self._batch_update -= 1
                should_render = self._batch_update == 0 and self.map_changed
            if should_render:
                self.render(True)

    def render_legend(self):
        with self.lock:
            is_over = self._is_over_legend_cap()
            listeners = list(self.listeners.values())
            was_suppressed = self._legend_suppressed
            if is_over:
                if was_suppressed:
                    return
                self._legend_suppressed = True
            else:
                if was_suppressed:
                    self._legend_suppressed = False
                objects_snapshot = list(self.objects.values())
                static_snapshot = list(self.legend_entries)
        if is_over and not was_suppressed:
            for l in listeners:
                l.at_legend_update([], False, self.name)
            return
        if not is_over:
            obj_entries = []
            for o in objects_snapshot:
                loc = o.location
                if loc is not None:
                    obj_entries.append(
                        (o.id, (o.symbol, o.name, (loc.coord.x, loc.coord.y)))
                    )
            static_entries = [(e.symbol, e.desc, e.coord) for e in static_snapshot]
            for l in listeners:
                entries = [e for oid, e in obj_entries if oid != l.id]
                entries.extend(static_entries)
                l.at_legend_update(entries, True, self.name)

    def render(self, force=False):
        with self.lock:
            needs_pre_render = (force or self.map_changed) and bool(self.pre_grid)
            self.map_changed = False
        if needs_pre_render:
            self.pre_render()

        t = time.time()
        # Keep the critical section tight: snapshot the collections under the
        # map lock, then read per-object state outside it. This avoids
        # acquiring object or node locks while holding the map lock, which
        # would invert the ordering used by movement and serialization paths.
        with self.lock:
            show_legend = not self._is_over_legend_cap()
            objects_snapshot = list(self.objects.values())
            static_snapshot = list(self.legend_entries)
            listeners = list(self.listeners.values())
            grid_snapshot = self.post_grid.copy()
        obj_entries = []
        for o in objects_snapshot:
            loc = o.location
            if loc is not None:
                obj_entries.append(
                    (o.id, (o.symbol, o.name, (loc.coord.x, loc.coord.y)))
                )
        static_entries = [(e.symbol, e.desc, e.coord) for e in static_snapshot]

        fps_limit = 1 / settings.MAP_FPS_LIMIT if settings.MAP_FPS_LIMIT > 0 else 0.0
        for l in listeners:
            if not getattr(l, "map_enabled", True):
                continue
            last_map_time = l.last_map_time
            if last_map_time and not force and fps_limit and (t - last_map_time) <= fps_limit:
                continue
            entries = [e for oid, e in obj_entries if oid != l.id]
            entries.extend(static_entries)
            grid_copy = grid_snapshot.copy()
            grid_copy = l.at_pre_map_render(grid_copy)
            map_str, min_x, max_y = MapInfo.render_grid(grid_copy)
            l.at_map_update(map_str, entries, min_x, max_y, show_legend, self.name)

    def add_legend_entry(self, entry: LegendEntry):
        with self.lock:
            self.legend_entries.append(entry)
            self.map_changed = True
        self.render_legend()

    def remove_legend_entry(self, entry: LegendEntry):
        with self.lock:
            self.legend_entries.remove(entry)
            self.map_changed = True
        self.render_legend()

    def add_listener(self, listener: Object, notify: bool = False):
        with self.lock:
            self.listeners[listener.id] = listener
        if notify:
            self.render(True)

    def remove_listener(self, listener: Object):
        with self.lock:
            self.listeners.pop(listener.id, None)

    def add_mapable(self, mapable: Object, notify: bool = True):
        with self.lock:
            self.objects[mapable.id] = mapable
        if notify:
            self.render_legend()

    def remove_mapable(self, mapable: Object):
        with self.lock:
            self.objects.pop(mapable.id, None)
        self.render_legend()

    def add_mapable_list(self, mapables: list[Object], notify: bool = True):
        with self.lock:
            self.objects.update({m.id: m for m in mapables})
        if notify:
            self.render_legend()


from atheriz.database_setup import get_database

class MapHandler:
    def __init__(self) -> None:
        self.lock = RLock()
        self.data: dict[tuple[str, int], MapInfo] = {}
        buffer: dict[tuple[str, int], MapInfo] = {}
        rows: list[tuple[str, int, bytes]] = []
        try:
            db = get_database()
            with db.lock:
                cursor = db.connection.cursor()
                cursor.execute("SELECT area, z, data FROM mapdata")
                try:
                    rows = cursor.fetchall()
                    if rows is None or (hasattr(rows, "_mock_name")):
                        rows = list(cursor)
                except Exception:
                    rows = list(cursor)
            for area, z, blob in rows:
                try:
                    mi = dill.loads(blob)
                    buffer[(area, z)] = mi
                except Exception as e:
                    logger.error(f"Error loading map chunk {area}:{z}: {e}")
            with self.lock:
                self.data.update(buffer)
        except Exception as e:
            logger.error(f"Error loading map data from DB: {e}")

    def save(self, force: bool = False):
        if not force and not settings.ALWAYS_SAVE_ALL:
            try:
                with self.lock:
                    if not any(
                        getattr(mi, "map_changed", False) or getattr(mi, "is_modified", False)
                        for mi in self.data.values()
                    ):
                        return
            except Exception:
                pass
        try:
            db = get_database()
        except RuntimeError:
            logger.warning("MapHandler.save: database closed, skipping")
            return
        try:
            with self.lock:
                refs = list(self.data.items())
        except Exception as e:
            logger.error(f"Error preparing map save: {e}")
            return
        snapshot: list[tuple[tuple[str, int], MapInfo]] = []
        to_clear: dict[tuple[str, int], MapInfo] = {}
        for k, mi in refs:
            try:
                with mi.lock:
                    was_changed = bool(getattr(mi, "map_changed", False) or getattr(mi, "is_modified", False))
                    mi_state = mi.__dict__.copy()
                    mi_state["pre_grid"] = dict(mi_state.get("pre_grid", {}))
                    mi_state["post_grid"] = dict(mi_state.get("post_grid", {}))
                    mi_state["legend_entries"] = list(mi_state.get("legend_entries", []))
                    mi_state["objects"] = {}
                    mi_state["listeners"] = {}
                    mi_state["_batch_update"] = 0
                    mi_state["_legend_suppressed"] = False
                    if was_changed:
                        mi.map_changed = False
                        if hasattr(mi, "is_modified"):
                            try:
                                object.__setattr__(mi, "is_modified", False)
                            except Exception:
                                mi.is_modified = False
                        to_clear[k] = mi
                mi_copy = MapInfo.__new__(MapInfo)
                mi_copy.__dict__.update(mi_state)
                mi_copy.lock = RLock()
                snapshot.append((k, mi_copy))
            except Exception as e:
                logger.error(f"Error preparing map save for {k}: {e}")
                # rollback already-cleared flag for this chunk if needed
                if was_changed:
                    try:
                        with mi.lock:
                            mi.map_changed = True
                    except Exception:
                        pass

        blobs: list[tuple[str, int, bytes]] = []
        for (area, z), mi in snapshot:
            try:
                blobs.append((area, z, dill.dumps(mi)))
            except Exception as e:
                logger.error(f"Error serializing map chunk {area}:{z}: {e}")
                k = (area, z)
                if k in to_clear:
                    try:
                        with to_clear[k].lock:
                            to_clear[k].map_changed = True
                    except Exception:
                        pass
        with db.lock:
            if getattr(db, "_closed", False) is True:
                logger.warning("MapHandler.save: database closed, skipping")
                for _, mi in to_clear.items():
                    try:
                        with mi.lock:
                            mi.map_changed = True
                    except Exception:
                        pass
                return
            try:
                cursor = db.connection.cursor()
                cursor.execute("BEGIN TRANSACTION")
            except Exception as e:
                logger.warning(f"MapHandler.save: database closed ({e}), skipping")
                for _, mi in to_clear.items():
                    try:
                        with mi.lock:
                            mi.map_changed = True
                    except Exception:
                        pass
                return
            try:
                for area, z, blob in blobs:
                    cursor.execute(
                        "INSERT OR REPLACE INTO mapdata (area, z, data) VALUES (?, ?, ?)",
                        (area, z, blob)
                    )
                cursor.execute("COMMIT")
                # flags already cleared optimistically; no post-commit wipe (avoids lost-update)
            except Exception as e:
                try:
                    cursor.execute("ROLLBACK")
                except Exception:
                    pass
                for _, mi in to_clear.items():
                    try:
                        with mi.lock:
                            mi.map_changed = True
                    except Exception:
                        pass
                logger.error(f"Error saving map data to DB: {e}")

    def set_mapinfo(self, area: str, z: int, mapinfo: MapInfo):
        with self.lock:
            self.data[(area, z)] = mapinfo

    def get_mapinfo(self, area: str, z: int):
        with self.lock:
            return self.data.get((area, z))

    def _get_or_create(self, area: str, z: int) -> MapInfo:
        with self.lock:
            mi = self.data.get((area, z))
            if mi is None:
                mi = MapInfo(name=area)
                self.data[(area, z)] = mi
            return mi

    def add_mapable(self, mapable: Object, notify: bool = False):
        """
        helper to add mapable to their current location's mapinfo
        """
        loc: Node | None = mapable.location
        if loc:
            mi = self._get_or_create(loc.coord.area, loc.coord.z)
            mi.add_mapable(mapable, notify=notify)

    def add_listener(self, listener: Object, notify: bool = False):
        """
        helper to add character as a listener to their current location's mapinfo
        """
        loc: Node | None = listener.location
        if loc:
            mi = self._get_or_create(loc.coord.area, loc.coord.z)
            mi.add_listener(listener, notify=notify)

    def remove_listener(self, listener: Object):
        """
        helper to remove listener from their current location's mapinfo
        """
        loc: Node | None = listener.location
        if loc:
            with self.lock:
                mi = self.data.get((loc.coord.area, loc.coord.z))
            if mi:
                mi.remove_listener(listener)

    def move_listener(
        self,
        listener: Object,
        to_coord: Coord,
        from_coord: Coord | None = None,
    ):
        from_map = None
        to_map = None
        with self.lock:
            if from_coord:
                from_map = self.data.get((from_coord.area, from_coord.z))
            to_map = self.data.get((to_coord.area, to_coord.z))
            if to_map is None:
                to_map = MapInfo(name=to_coord.area)
                self.data[(to_coord.area, to_coord.z)] = to_map
            if from_map is not None:
                from_map.remove_listener(listener)
            if to_map is not None:
                to_map.add_listener(listener)
        if from_map is not None:
            from_map.render(False)
        if to_map is not None:
            to_map.render(True)

    def move_mapable(
        self,
        mapable: Object,
        to_coord: Coord,
        from_coord: Coord | None = None,
    ):
        if from_coord and from_coord.area == to_coord.area and from_coord.z == to_coord.z:
            current_map = self._get_or_create(to_coord.area, to_coord.z)
            current_map.add_mapable(mapable)
            current_map.render(True)
            return
        from_map = None
        to_map = None
        with self.lock:
            if from_coord:
                from_map = self.data.get((from_coord.area, from_coord.z))
            to_map = self.data.get((to_coord.area, to_coord.z))
            if to_map is None:
                to_map = MapInfo(name=to_coord.area)
                self.data[(to_coord.area, to_coord.z)] = to_map
            if from_map is not None:
                from_map.remove_mapable(mapable)
            if to_map is not None:
                to_map.add_mapable(mapable)
        if from_map is not None:
            from_map.render(False)
        if to_map is not None:
            to_map.render(True)

    def remove_mapable(self, mapable: Object, from_area: str, from_z: int):
        with self.lock:
            from_map = self.data.get((from_area, from_z))
        if from_map:
            from_map.remove_mapable(mapable)
