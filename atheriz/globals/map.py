from __future__ import annotations
from threading import RLock
from atheriz.globals.node import Node
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.utils import Coord
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
    
    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            state.pop("objects", None)
            state.pop("listeners", None)
            return state
    
    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()
        self.objects: dict[int, Object] = {}
        self.listeners: dict[int, Object] = {}

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
        if grid.get((cx, cy + 1), None) in chars:
            n = True
        if grid.get((cx, cy - 1), None) in chars:
            s = True
        if grid.get((cx + 1, cy), None) in chars:
            e = True
        if grid.get((cx - 1, cy), None) in chars:
            w = True
        return n, s, e, w

    @staticmethod
    def render_char(
        grid: dict[tuple[int, int], str],
        original_grid: dict[tuple[int, int], str],
        char: str,
        style: str = "single",
    ) -> dict[tuple[int, int], str]:
        """
        renders specified char into appropriate road/wall/path type based on its neighbors
        """
        if not grid:
            return {}
        to_place = {}
        for k, v in grid.items():
            if v == char:
                n, s, e, w = MapInfo.get_dirs(original_grid, k, settings.ALL_SYMBOLS)
                if style == "single":
                    if n and s and e and w:
                        to_place[k] = "┼"
                    elif n and s and e:
                        to_place[k] = "├"
                    elif n and s and w:
                        to_place[k] = "┤"
                    elif n and e and w:
                        to_place[k] = "┴"
                    elif s and e and w:
                        to_place[k] = "┬"
                    elif n and e:
                        to_place[k] = "└"
                    elif n and w:
                        to_place[k] = "┘"
                    elif s and e:
                        to_place[k] = "┌"
                    elif s and w:
                        to_place[k] = "┐"
                    elif n and s:
                        to_place[k] = "│"
                    elif e and w:
                        to_place[k] = "─"
                    elif n:
                        to_place[k] = "│"
                    elif s:
                        to_place[k] = "│"
                    elif e:
                        to_place[k] = "─"
                    elif w:
                        to_place[k] = "─"
                    else:
                        to_place[k] = "─"
                elif style == "double":
                    if n and s and e and w:
                        to_place[k] = "╬"
                    elif n and s and e:
                        to_place[k] = "╠"
                    elif n and s and w:
                        to_place[k] = "╣"
                    elif n and e and w:
                        to_place[k] = "╩"
                    elif s and e and w:
                        to_place[k] = "╦"
                    elif n and e:
                        to_place[k] = "╚"
                    elif n and w:
                        to_place[k] = "╝"
                    elif s and e:
                        to_place[k] = "╔"
                    elif s and w:
                        to_place[k] = "╗"
                    elif n and s:
                        to_place[k] = "║"
                    elif e and w:
                        to_place[k] = "═"
                    elif n:
                        to_place[k] = "║"
                    elif s:
                        to_place[k] = "║"
                    elif e:
                        to_place[k] = "═"
                    elif w:
                        to_place[k] = "═"
                    else:
                        to_place[k] = "═"
                elif style == "rounded":
                    if n and s and e and w:
                        to_place[k] = "┼"
                    elif n and s and e:
                        to_place[k] = "├"
                    elif n and s and w:
                        to_place[k] = "┤"
                    elif n and e and w:
                        to_place[k] = "┴"
                    elif s and e and w:
                        to_place[k] = "┬"
                    elif n and e:
                        to_place[k] = "╰"
                    elif n and w:
                        to_place[k] = "╯"
                    elif s and e:
                        to_place[k] = "╭"
                    elif s and w:
                        to_place[k] = "╮"
                    elif n and s:
                        to_place[k] = "│"
                    elif e and w:
                        to_place[k] = "─"
                    elif n:
                        to_place[k] = "│"
                    elif s:
                        to_place[k] = "│"
                    elif e:
                        to_place[k] = "─"
                    elif w:
                        to_place[k] = "─"
                    else:
                        to_place[k] = "─"
        grid.update(to_place)
        return grid

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
        with self.lock:
            self.post_grid = rendered

    def update_grid(self, coord: tuple[int, int], new_symbol: str):
        with self.lock:
            self.pre_grid[coord] = new_symbol
            self.map_changed = True
        self.render(True)

    def render_legend(self):
        with self.lock:
            if len(self.objects) + len(self.legend_entries) > settings.MAX_OBJECTS_PER_LEGEND:
                return
            # Pre-compute entries once, tagged with source id for per-listener filtering
            obj_entries = [
                (o.id, (o.symbol, o.name, (o.location.coord.x, o.location.coord.y)))
                for o in self.objects.values()
            ]
            static_entries = [(e.symbol, e.desc, e.coord) for e in self.legend_entries]
            listeners = list(self.listeners.values())
        for l in listeners:
            entries = [e for oid, e in obj_entries if oid != l.id]
            entries.extend(static_entries)
            l.at_legend_update(entries, True, self.name)

    def render(self, force=False):
        # Atomically read and reset map_changed to prevent a race where
        # update_grid() sets it True between our check and our reset.
        with self.lock:
            needs_pre_render = (force or self.map_changed) and bool(self.pre_grid)
            self.map_changed = False
        if needs_pre_render:
            self.pre_render()

        t = time.time()
        # Snapshot everything needed under the lock, then do per-listener
        # work (at_pre_map_render, render_grid, at_map_update) outside it
        # to keep the critical section tight.
        with self.lock:
            show_legend = (
                len(self.objects) + len(self.legend_entries) <= settings.MAX_OBJECTS_PER_LEGEND
            )
            obj_entries = [
                (o.id, (o.symbol, o.name, (o.location.coord.x, o.location.coord.y)))
                for o in self.objects.values()
            ]
            static_entries = [(e.symbol, e.desc, e.coord) for e in self.legend_entries]
            listeners = list(self.listeners.values())
            grid_snapshot = self.post_grid.copy()

        fps_limit = 1 / settings.MAP_FPS_LIMIT
        for l in listeners:
            last_map_time = l.last_map_time
            if last_map_time and not force and (t - last_map_time) <= fps_limit:
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
        self.render_legend()

    def remove_legend_entry(self, entry: LegendEntry):
        with self.lock:
            self.legend_entries.remove(entry)
        self.render_legend()

    def add_listener(self, listener: Object):
        with self.lock:
            self.listeners[listener.id] = listener

    def remove_listener(self, listener: Object):
        with self.lock:
            self.listeners.pop(listener.id, None)

    def add_mapable(self, mapable: Object):
        with self.lock:
            self.objects[mapable.id] = mapable
        self.render_legend()

    def remove_mapable(self, mapable: Object):
        with self.lock:
            self.objects.pop(mapable.id, None)
        self.render_legend()

    def add_mapable_list(self, mapables: list[Object]):
        with self.lock:
            self.objects.update({m.id: m for m in mapables})
        self.render_legend()


from atheriz.database_setup import get_database

class MapHandler:
    def __init__(self) -> None:
        self.lock = RLock()
        self.data: dict[tuple[str, int], MapInfo] = {}
        
        try:
            db = get_database()
            cursor = db.connection.cursor()
            cursor.execute("SELECT area, z, data FROM mapdata")
            for area, z, blob in cursor:
                try:
                    mi = dill.loads(blob)
                    self.data[(area, z)] = mi
                except Exception as e:
                    logger.error(f"Error loading map chunk {area}:{z}: {e}")
        except Exception as e:
            logger.error(f"Error loading map data from DB: {e}")

    def save(self):
        db = get_database()
        cursor = db.connection.cursor()
        
        with self.lock:
            snapshot = list(self.data.items())
        
        with db.lock:
            cursor.execute("BEGIN TRANSACTION")
            try:
                for (area, z), mi in snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO mapdata (area, z, data) VALUES (?, ?, ?)",
                        (area, z, dill.dumps(mi))
                    )
                cursor.execute("COMMIT")
            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Error saving map data to DB: {e}")

    def set_mapinfo(self, area: str, z: int, mapinfo: MapInfo):
        with self.lock:
            self.data[(area, z)] = mapinfo

    def get_mapinfo(self, area: str, z: int):
        with self.lock:
            return self.data.get((area, z))

    def add_mapable(self, mapable: Object):
        """
        helper to add mapable to their current location's mapinfo
        """
        loc: Node | None = mapable.location
        if loc:
            with self.lock:
                mi = self.data.get((loc.coord.area, loc.coord.z))
            if mi:
                mi.add_mapable(mapable)
                mi.render()
            else:
                mi = MapInfo(name=loc.coord.area)
                mi.add_mapable(mapable)
                self.set_mapinfo(loc.coord.area, loc.coord.z, mi)
                mi.render()

    def add_listener(self, listener: Object):
        """
        helper to add character as a listener to their current location's mapinfo
        """
        loc: Node | None = listener.location
        if loc:
            with self.lock:
                mi = self.data.get((loc.coord.area, loc.coord.z))
            if mi:
                mi.add_listener(listener)
            else:
                mi = MapInfo(name=loc.coord.area)
                mi.add_listener(listener)
                self.set_mapinfo(loc.coord.area, loc.coord.z, mi)

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
        # if from_coord and from_coord.area == to_coord.area and from_coord.z == to_coord.z:
        #     return
        from_map = None
        with self.lock:
            if from_coord:
                from_map = self.data.get((from_coord.area, from_coord.z))
            to_map = self.data.get((to_coord.area, to_coord.z))
        if not to_map:
            to_map = MapInfo()
            self.set_mapinfo(to_coord.area, to_coord.z, to_map)
        if from_map:
            from_map.remove_listener(listener)
        if to_map:
            to_map.add_listener(listener)

    def move_mapable(
        self,
        mapable: Object,
        to_coord: Coord,
        from_coord: Coord | None = None,
    ):
        if from_coord and from_coord.area == to_coord.area and from_coord.z == to_coord.z:
            with self.lock:
                current_map = self.data.get((to_coord.area, to_coord.z))
            if current_map:
                current_map.add_mapable(mapable)
                current_map.render(True)
            else:
                current_map = MapInfo()
                self.set_mapinfo(to_coord.area, to_coord.z, current_map)
                current_map.add_mapable(mapable)
                current_map.render(True)
            return
        from_map = None
        with self.lock:
            if from_coord:
                from_map = self.data.get((from_coord.area, from_coord.z))
            to_map = self.data.get((to_coord.area, to_coord.z))
        if not to_map:
            to_map = MapInfo()
            self.set_mapinfo(to_coord.area, to_coord.z, to_map)
        if from_map:
            from_map.remove_mapable(mapable)
            from_map.render(True)
        if to_map:
            to_map.add_mapable(mapable)
            to_map.render(True)

    def remove_mapable(self, mapable: Object, from_area: str, from_z: int):
        with self.lock:
            from_map = self.data.get((from_area, from_z))
        if from_map:
            from_map.remove_mapable(mapable)
            from_map.render_legend()
