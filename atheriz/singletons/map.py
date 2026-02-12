# import itertools
from atheriz.utils import (
    wrap_truecolor,
    wrap_xterm256,
    strip_ansi,
    get_import_path,
    instance_from_string,
    tuple_to_str,
    str_to_tuple,
)
from threading import Lock, RLock
from atheriz.singletons.node import Node
from pathlib import Path
from atheriz.logger import logger
import atheriz.settings as settings
import json
import time
import copy
from typing import TYPE_CHECKING, Any
from time import sleep

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


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

    def __getstate__(self):
        d = self.__dict__.copy()
        d["coord"] = tuple_to_str(d["coord"])
        return d

    def __setstate__(self, state):
        if state:
            self.__dict__.update(state)
            self.coord = str_to_tuple(state["coord"])


class MapInfo:
    def __init__(
        self,
        name: str = "unknown",
        pre_grid: dict[tuple[int, int], str] = {},
        post_grid: dict[tuple[int, int], str] = {},
        legend_entries: list[LegendEntry] = [],
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
        state = self.__dict__.copy()
        del state["lock"]
        del state["objects"]
        del state["listeners"]
        state["__import_path__"] = get_import_path(self)
        if self.legend_entries:
            entries = []
            for entry in self.legend_entries:
                entries.append(entry.__getstate__())
            state["legend_entries"] = entries
        if self.pre_grid:
            pre_grid = {}
            for k, v in self.pre_grid.items():
                pre_grid[tuple_to_str(k)] = v
            state["pre_grid"] = pre_grid
        if self.post_grid:
            post_grid = {}
            for k, v in self.post_grid.items():
                post_grid[tuple_to_str(k)] = v
            state["post_grid"] = post_grid

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()
        self.objects: dict[int, Object] = {}
        self.listeners: dict[int, Object] = {}
        if state.get("legend_entries"):
            entries = []
            for entry_state in state["legend_entries"]:
                entry = LegendEntry()
                entry.__setstate__(entry_state)
                entries.append(entry)
            self.legend_entries = entries
        else:
            self.legend_entries = []
        if state.get("pre_grid"):
            pre_grid = {}
            for k, v in state["pre_grid"].items():
                pre_grid[str_to_tuple(k)] = v
            self.pre_grid = pre_grid
        if state.get("post_grid"):
            post_grid = {}
            for k, v in state["post_grid"].items():
                post_grid[str_to_tuple(k)] = v
            self.post_grid = post_grid

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
            print("grid is empty")
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
        grid: dict[tuple[int, int], str], coord: tuple[int, int], char: str
    ) -> tuple[bool, bool, bool, bool]:
        """
        returns a tuple of booleans representing the directions of the walls around a coordinate
        """
        n = False
        s = False
        e = False
        w = False
        cx, cy = coord
        if grid.get((cx, cy + 1), None) == char:
            n = True
        if grid.get((cx, cy - 1), None) == char:
            s = True
        if grid.get((cx + 1, cy), None) == char:
            e = True
        if grid.get((cx - 1, cy), None) == char:
            w = True
        return n, s, e, w

    @staticmethod
    def render_char(
        grid: dict[tuple[int, int], str], char: str, style: str = "single"
    ) -> dict[tuple[int, int], str]:
        """
        renders specified char into appropriate road/wall/path type based on its neighbors
        """
        if not grid:
            return {}
        to_place = {}
        for k, v in grid.items():
            if v == char:
                n, s, e, w = MapInfo.get_dirs(grid, k, char)
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

    def pre_render(self):
        with self.lock:
            rendered = copy.deepcopy(self.pre_grid)
        MapInfo.render_char(rendered, settings.SINGLE_WALL_PLACEHOLDER, "single")
        MapInfo.render_char(rendered, settings.DOUBLE_WALL_PLACEHOLDER, "double")
        MapInfo.render_char(rendered, settings.ROUNDED_WALL_PLACEHOLDER, "rounded")
        MapInfo.render_char(rendered, settings.PATH_PLACEHOLDER, "rounded")
        MapInfo.render_char(rendered, settings.ROAD_PLACEHOLDER, "double")
        rooms = []
        for k, v in rendered.items():
            if v == settings.ROOM_PLACEHOLDER:
                rooms.append(k)
        for room in rooms:
            rendered[room] = " "
        with self.lock:
            # print("rendered = ", rendered)
            self.post_grid = rendered

    def update_grid(self, coord: tuple[int, int], new_symbol: str):
        with self.lock:
            self.pre_grid[coord] = new_symbol
            self.map_changed = True
        self.render(True)

    def render_legend(self):
        with self.lock:
            for l in self.listeners.values():
                entries = [
                    (o.symbol, o.name, (o.location.coord[1], o.location.coord[2]))
                    for o in self.objects.values()
                    if o.id != l.id
                ]
                entries.extend([(e.symbol, e.desc, e.coord) for e in self.legend_entries])
                l.at_legend_update(entries, self.name)

    def render(self, force=False):
        # print("rendering map")
        if force or self.map_changed:
            if self.pre_grid:
                self.pre_render()
            self.map_changed = False
        t = time.time()
        with self.lock:
            for l in self.listeners.values():
                entries = [
                    (o.symbol, o.name, (o.location.coord[1], o.location.coord[2]))
                    for o in self.objects.values()
                    if o.id != l.id
                ]
                entries.extend([(e.symbol, e.desc, e.coord) for e in self.legend_entries])
                grid_copy = self.post_grid.copy()
                # grid_copy = copy.deepcopy(self.post_grid)
                # l.at_legend_update(list(mapables.values()) + legend_entries)
                last_map_time = l.last_map_time
                if last_map_time:
                    if t - last_map_time > 1 / settings.MAP_FPS_LIMIT or force:
                        grid_copy = l.at_pre_map_render(grid_copy)
                        map_str, min_x, max_y = MapInfo.render_grid(grid_copy)
                        l.at_map_update(map_str, entries, min_x, max_y, self.name)
                else:
                    grid_copy = l.at_pre_map_render(grid_copy)
                    map_str, min_x, max_y = MapInfo.render_grid(grid_copy)
                    l.at_map_update(map_str, entries, min_x, max_y, self.name)

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
            self.objects.update(dict([(m.id, m) for m in mapables]))
        self.render_legend()


def _load_file(filename: str) -> dict[str, Any]:
    path = Path(settings.SAVE_PATH) / filename
    if not path.exists():
        logger.warning(f"File {filename} does not exist.")
        return {}
    with path.open("r") as f:
        return json.load(f)


def _save_file(data: Any, filename: str):
    path = Path(settings.SAVE_PATH) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w") as f:
        json.dump(data, f)
    temp_path.replace(path)


class MapHandler:
    def __init__(self) -> None:
        mapdata = _load_file("mapdata")
        if mapdata:
            new_data = {}
            for k, v in mapdata.items():
                mi = MapInfo()
                mi.__setstate__(v)
                new_data[str_to_tuple(k)] = mi
            self.data = new_data
        else:
            self.data: dict[tuple[str, int], MapInfo] = {}
        self.lock = RLock()

    def save(self):
        logger.info("Saving map data...")
        data = {}
        with self.lock:
            for k, v in self.data.items():
                data[tuple_to_str(k)] = v.__getstate__()
        _save_file(data, "mapdata")

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
                mi = self.data.get((loc.coord[0], loc.coord[3]))
            if mi:
                mi.add_mapable(mapable)
                mi.render()
            else:
                mi = MapInfo(name=loc.coord[0])
                mi.add_mapable(mapable)
                self.set_mapinfo(loc.coord[0], loc.coord[3], mi)
                mi.render()

    def add_listener(self, listener: Object):
        """
        helper to add character as a listener to their current location's mapinfo
        """
        loc: Node | None = listener.location
        if loc:
            with self.lock:
                mi = self.data.get((loc.coord[0], loc.coord[3]))
            if mi:
                mi.add_listener(listener)
            else:
                mi = MapInfo(name=loc.coord[0])
                mi.add_listener(listener)
                self.set_mapinfo(loc.coord[0], loc.coord[3], mi)

    def remove_listener(self, listener: Object):
        """
        helper to remove listener from their current location's mapinfo
        """
        loc: Node | None = listener.location
        if loc:
            with self.lock:
                mi = self.data.get((loc.coord[0], loc.coord[3]))
            if mi:
                mi.remove_listener(listener)

    def move_listener(
        self,
        listener: Object,
        to_coord: tuple[str, int, int, int],
        from_coord: tuple[str, int, int, int] | None = None,
    ):
        if from_coord and from_coord[0] == to_coord[0] and from_coord[3] == to_coord[3]:
            return
        from_map = None
        with self.lock:
            if from_coord:
                from_map = self.data.get((from_coord[0], from_coord[3]))
            to_map = self.data.get((to_coord[0], to_coord[3]))
        if not to_map:
            to_map = MapInfo()
            self.set_mapinfo(to_coord[0], to_coord[3], to_map)
        if from_map:
            from_map.remove_listener(listener)
        if to_map:
            to_map.add_listener(listener)

    def move_mapable(
        self,
        mapable: Object,
        to_coord: tuple[str, int, int, int],
        from_coord: tuple[str, int, int, int] | None = None,
    ):
        if from_coord and from_coord[0] == to_coord[0] and from_coord[3] == to_coord[3]:
            with self.lock:
                current_map = self.data.get((to_coord[0], to_coord[3]))
            if current_map:
                current_map.add_mapable(mapable)
                current_map.render(True)
            else:
                current_map = MapInfo()
                self.set_mapinfo(to_coord[0], to_coord[3], current_map)
                current_map.add_mapable(mapable)
                current_map.render(True)
            return
        from_map = None
        with self.lock:
            if from_coord:
                from_map = self.data.get((from_coord[0], from_coord[3]))
            to_map = self.data.get((to_coord[0], to_coord[3]))
        if not to_map:
            to_map = MapInfo()
            self.set_mapinfo(to_coord[0], to_coord[3], to_map)
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


# class FakeListener:
#     def __init__(self):
#         self.key = 'test'

# poi: list[list] = []
# poi.append([None, '↑', 't'])
# poi.append([None, 'x', 'xxxxx'])
# poi.append([None, 'y', 'yyy'])
# poi.append([None, 'z', 'zzzzzzzzz'])
# poi.append([None, '↑', 't'])
# poi.append([None, 'x', 'x'])
# poi.append([None, 'y', 'yyy'])
# poi.append([None, 'z', 'z'])
# poi.append([None, '↑', 't'])
# poi.append([None, 'x', 'x'])
# poi.append([None, 'y', 'yyy'])
# poi.append([None, 'z', 'z'])
# poi.append([None, '↑', 't'])
# poi.append([None, 'x', 'xxxxx'])
# poi.append([None, 'y', 'yyy'])
# poi.append([None, 'z', 'zzzzzzzzz'])
# listener = FakeListener()

# mi = MapInfo([],0,0,poi,{})
# legend = mi.gen_legend(listener,{},"Test map")
# print(legend)
