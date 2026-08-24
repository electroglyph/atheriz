from __future__ import annotations
from atheriz.globals.get import get_map_handler, get_id, set_id
from atheriz.globals.objects import get, add_object, remove_object
from threading import RLock
from typing import TYPE_CHECKING
from atheriz.logger import logger
import dill
from atheriz.objects.nodes import Node, NodeArea, NodeGrid, Transition
from atheriz.objects.base_door import Door
from atheriz.utils import Coord, detach

if TYPE_CHECKING:
    from atheriz.objects.nodes import Transition
    from atheriz.objects.base_door import Door

from atheriz.database_setup import get_database
import atheriz.settings as settings
import sqlite3
import copy


class NodeHandler:
    def __init__(self):
        # this guards self.areas:
        self.lock = RLock()
        # this guards self.transitions:
        self.lock2 = RLock()
        self.areas: dict[str, NodeArea] = {}
        # these keep track of transitions between different areas
        self.transitions: dict[Coord, Transition] = {}
        # guards self.doors:
        self.lock3 = RLock()
        self.doors: dict[Coord, dict[str, Door]] = {}
        self._modified = False

        self.load()

    def load(self):
        """Load node data from the database."""
        try:
            db = get_database()
            with db.lock:
                cursor = db.connection.cursor()
                cursor.execute("SELECT name, data FROM areas")
                for name, blob in cursor:
                    try:
                        self.areas[name] = dill.loads(blob)
                    except Exception as e:
                        logger.error(f"Error loading area {name}: {e}")
                cursor.execute("SELECT to_area, to_x, to_y, to_z, data FROM transitions")
                for area, x, y, z, blob in cursor:
                    try:
                        self.transitions[Coord(area, x, y, z)] = dill.loads(blob)
                    except Exception as e:
                        logger.error(f"Error loading transition to {area},{x},{y},{z}: {e}")
                cursor.execute("SELECT area, x, y, z, data FROM doors")
                for area, x, y, z, blob in cursor:
                    try:
                        self.doors[Coord(area, x, y, z)] = dill.loads(blob)
                    except Exception as e:
                        logger.error(f"Error loading doors at {area},{x},{y},{z}: {e}")
        except Exception as e:
            logger.error(f"Error loading node data from DB: {e}")
            return
        max_node_id = 0
        for area in list(self.areas.values()):
            try:
                for grid in list(area.grids.values()):
                    for node in list(grid.nodes.values()):
                        try:
                            if hasattr(node, "resolve_relations"):
                                node.resolve_relations()
                            if node.id is not None and node.id > max_node_id:
                                max_node_id = node.id
                            existing = get(node.id)
                            if existing and existing[0] is not node:
                                logger.warning(
                                    f"Node id collision on load: id {node.id} already mapped to {existing[0]}"
                                )
                            add_object(node)
                        except Exception as e:
                            logger.error(f"Error resolving node {getattr(node, 'id', '?')} in area {getattr(area, 'name', '?')}: {e}")
            except Exception as e:
                logger.error(f"Error resolving area {getattr(area, 'name', '?')}: {e}")
        if max_node_id:
            set_id(max(get_id(), max_node_id))

    def _is_dirty(self):
        with self.lock:
            areas = list(self.areas.values())
            if self._modified:
                return True
        for a in areas:
            with a.lock:
                if getattr(a, "is_modified", False):
                    return True
                grids = list(a.grids.values())
            for g in grids:
                with g.lock:
                    if getattr(g, "is_modified", False):
                        return True
                    nodes = list(g.nodes.values())
                for n in nodes:
                    try:
                        with n.lock:
                            if getattr(n, "is_modified", False):
                                return True
                    except Exception:
                        pass
        with self.lock2:
            if self._modified:
                return True
        with self.lock3:
            if self._modified:
                return True
        return False

    def save(self, force=False):
        if not force and not settings.ALWAYS_SAVE_ALL and not self._is_dirty():
            return
        try:
            db = get_database()
        except RuntimeError:
            logger.warning("NodeHandler.save: database closed, skipping")
            return
        with self.lock:
            area_refs = list(self.areas.values())
            handler_was = self._modified
            if handler_was:
                self._modified = False
        handler_cleared = handler_was
        with self.lock2:
            trans_refs = list(self.transitions.values())
        transitions_snapshot = []
        for t in trans_refs:
            try:
                lock = getattr(t, "lock", None)
                if lock is not None:
                    with lock:
                        t_state = t.__dict__.copy()
                else:
                    t_state = t.__dict__.copy()
                t_copy = Transition.__new__(Transition)
                t_copy.__dict__.update(t_state)
                t_copy.lock = RLock()
                transitions_snapshot.append(t_copy)
            except Exception as e:
                logger.error(f"Error detaching transition {t}: {e}")
        with self.lock3:
            doors_refs = [(k, dict(v)) for k, v in self.doors.items()]
        doors_snapshot = []
        for k, doors_dict in doors_refs:
            doors_copy = {}
            for dk, door in doors_dict.items():
                try:
                    lock = getattr(door, "lock", None)
                    if lock is not None:
                        with lock:
                            door_state = door.__dict__.copy()
                    else:
                        door_state = door.__dict__.copy()
                    door_copy = Door.__new__(Door)
                    door_copy.__dict__.update(door_state)
                    door_copy.lock = RLock()
                    doors_copy[dk] = door_copy
                except Exception as e:
                    logger.error(f"Error detaching door {dk} at {k}: {e}")
            doors_snapshot.append((k, doors_copy))
        areas_snapshot = []
        cleared_areas: list[NodeArea] = []
        cleared_grids: list[NodeGrid] = []
        cleared_nodes: list[Node] = []
        for a in area_refs:
            with a.lock:
                was_area = a.is_modified
                grids_snapshot = dict(a.grids)
                a_data = dict(a.data)
                a_name = a.name
                a_theme = a.theme
                a_linked = set(a.linked_areas) if a.linked_areas else None
                if was_area:
                    a.is_modified = False
                    cleared_areas.append(a)
            detached_grids: dict[int, NodeGrid] = {}
            local_grids: list[NodeGrid] = []
            local_nodes: list[Node] = []
            grid_failed = False
            for z, g in grids_snapshot.items():
                with g.lock:
                    was_grid = g.is_modified
                    nodes_snapshot = dict(g.nodes)
                    g_data = dict(g.data)
                    g_area = g.area
                    g_z = g.z
                    if was_grid:
                        g.is_modified = False
                        local_grids.append(g)
            # build detached nodes per grid outside g.lock
                detached_nodes: dict[tuple[int, int], Node] = {}
                for coord, n in nodes_snapshot.items():
                    try:
                        with n.lock:
                            was_node = n.is_modified
                            n_state = n.__dict__.copy()
                            if "_contents" in n_state:
                                n_state["_contents"] = set(n_state["_contents"])
                            if "links" in n_state:
                                n_state["links"] = list(n_state["links"])
                            if "nouns" in n_state:
                                n_state["nouns"] = dict(n_state["nouns"])
                            if "scripts" in n_state:
                                n_state["scripts"] = set(n_state["scripts"])
                            if "hooks" in n_state:
                                n_state["hooks"] = {}
                            if "tags" in n_state:
                                n_state["tags"] = set(n_state["tags"])
                            n_state["is_modified"] = False
                            if was_node:
                                n.is_modified = False
                                local_nodes.append(n)
                    except Exception:
                        continue
                    try:
                        detached_node = Node.__new__(Node)
                        detached_node.__dict__.update(n_state)
                        detached_node.lock = RLock()
                        detached_nodes[coord] = detached_node
                    except Exception as e:
                        logger.error(f"Error detaching node {getattr(n, 'id', '?')}: {e}")
                        if was_node:
                            try:
                                with n.lock:
                                    n.is_modified = True
                            except Exception:
                                pass
                            if n in local_nodes:
                                local_nodes.remove(n)
                        continue
                try:
                    detached_grid = NodeGrid.__new__(NodeGrid)
                    detached_grid.area = g_area
                    detached_grid.z = g_z
                    detached_grid.is_modified = False
                    detached_grid.nodes = detached_nodes
                    detached_grid.data = g_data
                    detached_grid.lock = RLock()
                    detached_grids[z] = detached_grid
                except Exception as e:
                    logger.error(f"Error detaching grid {g_z} in area {a_name}: {e}")
                    if was_grid:
                        try:
                            with g.lock:
                                g.is_modified = True
                        except Exception:
                            pass
                        if g in local_grids:
                            local_grids.remove(g)
                    for n in list(detached_nodes.values()):
                        pass
                    for n in nodes_snapshot.values():
                        if n in local_nodes:
                            try:
                                with n.lock:
                                    n.is_modified = True
                            except Exception:
                                pass
                            local_nodes.remove(n)
                    grid_failed = True
                    continue
            if grid_failed and not detached_grids and was_area and not local_grids and not local_nodes:
                try:
                    with a.lock:
                        a.is_modified = True
                except Exception:
                    pass
                if a in cleared_areas:
                    cleared_areas.remove(a)
                for g in local_grids:
                    try:
                        with g.lock:
                            g.is_modified = True
                    except Exception:
                        pass
                    if g in cleared_grids:
                        cleared_grids.remove(g)
                for n in local_nodes:
                    try:
                        with n.lock:
                            n.is_modified = True
                    except Exception:
                        pass
                continue
            try:
                detached_area = NodeArea.__new__(NodeArea)
                detached_area.name = a_name
                detached_area.theme = a_theme
                detached_area.is_modified = False
                detached_area.grids = detached_grids
                detached_area.data = a_data
                detached_area.linked_areas = a_linked
                detached_area.lock = RLock()
                blob = detach(detached_area)
                areas_snapshot.append(blob)
                cleared_grids.extend(local_grids)
                cleared_nodes.extend(local_nodes)
            except Exception as e:
                logger.error(f"Error detaching area {a_name}: {e}")
                if was_area:
                    try:
                        with a.lock:
                            a.is_modified = True
                    except Exception:
                        pass
                    if a in cleared_areas:
                        cleared_areas.remove(a)
                for g in local_grids:
                    try:
                        with g.lock:
                            g.is_modified = True
                    except Exception:
                        pass
                for n in local_nodes:
                    try:
                        with n.lock:
                            n.is_modified = True
                    except Exception:
                        pass
                continue
        if not areas_snapshot and not transitions_snapshot and not doors_snapshot:
            if handler_cleared:
                with self.lock:
                    self._modified = True
            for a in cleared_areas:
                with a.lock:
                    a.is_modified = True
            for g in cleared_grids:
                with g.lock:
                    g.is_modified = True
            for n in cleared_nodes:
                try:
                    with n.lock:
                        n.is_modified = True
                except Exception:
                    pass
            return
        with db.lock:
            if getattr(db, "_closed", False) is True:
                logger.warning("NodeHandler.save: database closed, skipping")
                if handler_cleared:
                    with self.lock:
                        self._modified = True
                for a in cleared_areas:
                    with a.lock:
                        a.is_modified = True
                for g in cleared_grids:
                    with g.lock:
                        g.is_modified = True
                for n in cleared_nodes:
                    try:
                        with n.lock:
                            n.is_modified = True
                    except Exception:
                        pass
                return
            try:
                cursor = db.connection.cursor()
                cursor.execute("BEGIN TRANSACTION")
            except sqlite3.ProgrammingError as e:
                logger.warning(f"NodeHandler.save: database closed ({e}), skipping")
                if handler_cleared:
                    with self.lock:
                        self._modified = True
                for a in cleared_areas:
                    with a.lock:
                        a.is_modified = True
                for g in cleared_grids:
                    with g.lock:
                        g.is_modified = True
                for n in cleared_nodes:
                    try:
                        with n.lock:
                            n.is_modified = True
                    except Exception:
                        pass
                return
            try:
                for area in areas_snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO areas (name, data) VALUES (?, ?)",
                        (area.name, dill.dumps(area)),
                    )
                for t in transitions_snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO transitions (to_area, to_x, to_y, to_z, data) VALUES (?, ?, ?, ?, ?)",
                        (t.to_coord.area, t.to_coord.x, t.to_coord.y, t.to_coord.z, dill.dumps(t)),
                    )
                for coord, doors_dict in doors_snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO doors (area, x, y, z, data) VALUES (?, ?, ?, ?, ?)",
                        (coord.area, coord.x, coord.y, coord.z, dill.dumps(doors_dict)),
                    )
                cursor.execute("COMMIT")
            except Exception as e:
                try:
                    cursor.execute("ROLLBACK")
                except sqlite3.ProgrammingError:
                    pass
                logger.error(f"Error saving node data to DB: {e}")
                if handler_cleared:
                    with self.lock:
                        self._modified = True
                for a in cleared_areas:
                    with a.lock:
                        a.is_modified = True
                for g in cleared_grids:
                    with g.lock:
                        g.is_modified = True
                for n in cleared_nodes:
                    try:
                        with n.lock:
                            n.is_modified = True
                    except Exception:
                        pass
                return

    def get_doors(self, coord: Coord) -> dict[str, Door] | None:
        with self.lock3:
            d = self.doors.get(coord)
            return d

    def add_door(self, door: Door):
        with self.lock3:
            d = self.doors.get(door.from_coord)
            if d:
                d[door.from_exit] = door
            else:
                d = {door.from_exit: door}
                self.doors[door.from_coord] = d
            d = self.doors.get(door.to_coord)
            if d:
                d[door.to_exit] = door
            else:
                d = {door.to_exit: door}
                self.doors[door.to_coord] = d
            self._modified = True
        mh = get_map_handler()
        mi = mh.get_mapinfo(door.to_coord.area, door.to_coord.z)
        if mi:
            symbol = door.closed_symbol if door.closed else door.open_symbol
            with mi.lock:
                mi.post_grid[door.symbol_coord] = symbol
                if mi.pre_grid:
                    mi.pre_grid[door.symbol_coord] = symbol
                    mi.map_changed = True
            mi.render(True)

    def remove_door(self, door: Door):
        with self.lock3:
            d = self.doors.get(door.from_coord)
            rem_keys = []
            if d:
                for k, v in d.items():
                    if v == door:
                        rem_keys.append(k)
                for k in rem_keys:
                    del d[k]
            rem_keys.clear()
            d = self.doors.get(door.to_coord)
            if d:
                for k, v in d.items():
                    if v == door:
                        rem_keys.append(k)
                for k in rem_keys:
                    del d[k]
            self._modified = True
        mh = get_map_handler()
        mi = mh.get_mapinfo(door.to_coord.area, door.to_coord.z)
        if mi:
            mi.update_grid(door.symbol_coord, " ")
            mi.render(True)

    def add_node(self, node: Node):
        area = self.get_area(node.coord.area)
        if area:
            grid = area.get_grid(node.coord.z)
            if grid:
                grid.add_node(node)
            else:
                grid = NodeGrid(node.coord.area, node.coord.z)
                grid.add_node(node)
                area.add_grid(grid)
        else:
            area = NodeArea(node.coord.area)
            grid = NodeGrid(node.coord.area, node.coord.z)
            grid.add_node(node)
            area.add_grid(grid)
            self.add_area(area)
        with self.lock:
            self._modified = True

    def add_area(self, area: NodeArea):
        with self.lock:
            self.areas[area.name] = area
            self._modified = True

    def remove_area(self, name: str):
        with self.lock:
            area = self.areas.pop(name, None)
            if area:
                area.clear()
            self._modified = True

    def clear(self):
        with self.lock:
            for v in self.areas.values():
                for grid in v.grids.values():
                    for node in grid.nodes.values():
                        remove_object(node)
                v.clear()
            self.areas.clear()
            self._modified = True
        with self.lock2:
            self.transitions.clear()
            self._modified = True
        with self.lock3:
            self.doors.clear()
            self._modified = True

    def get_area(self, name: str) -> NodeArea | None:
        with self.lock:
            return self.areas.get(name)

    def get_areas(self) -> list[NodeArea]:
        with self.lock:
            return [x for x in self.areas.values()]

    def get_node(self, coord: Coord) -> Node | None:
        area = self.get_area(coord.area)
        if area:
            grid = area.get_grid(coord.z)
            if grid:
                return grid.get_node((coord.x, coord.y))
        return None

    def remove_node(self, coord: Coord):
        node = self.get_node(coord)
        area = self.get_area(coord.area)
        if area:
            grid = area.get_grid(coord.z)
            if grid:
                grid.remove_node((coord.x, coord.y))
        if node:
            remove_object(node)
        with self.lock:
            self._modified = True

    def get_nodes(self, coords: list[Coord]) -> list:
        result = []
        for c in coords:
            n = self.get_node(c)
            if n:
                result.append(n)
        return result

    def add_transition(self, transition: Transition):
        with self.lock2:
            self.transitions[transition.to_coord] = transition
            self._modified = True

    def remove_transition(self, destination: Coord):
        with self.lock2:
            self.transitions.pop(destination, None)
            self._modified = True

    def find_transitions(
        self, from_z=None, to_z=None, from_area=None, to_area=None
    ) -> list[Transition]:
        result = []
        required_matches = 0
        if from_z is not None:
            required_matches += 1
        if to_z is not None:
            required_matches += 1
        if from_area is not None:
            required_matches += 1
        if to_area is not None:
            required_matches += 1
        with self.lock2:
            for t in self.transitions.values():
                matches = 0
                if from_z is not None and t.from_coord.z == from_z:
                    matches += 1
                if to_z is not None and t.to_coord.z == to_z:
                    matches += 1
                if from_area is not None and t.from_coord.area == from_area:
                    matches += 1
                if to_area is not None and t.to_coord.area == to_area:
                    matches += 1
                if matches == required_matches:
                    result.append(t)
        return result
