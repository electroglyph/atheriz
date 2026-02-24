from __future__ import annotations
from threading import RLock
from typing import TYPE_CHECKING
from atheriz.logger import logger
import dill
from atheriz.objects.nodes import Node, NodeArea, NodeGrid

if TYPE_CHECKING:
    from atheriz.objects.nodes import Door, Transition

from atheriz.database_setup import get_database


class NodeHandler:
    def __init__(self):
        # this guards self.areas:
        self.lock = RLock()
        # this guards self.transitions:
        self.lock2 = RLock()
        self.areas: dict[str, NodeArea] = {}
        # these keep track of transitions between different areas
        self.transitions: dict[tuple[str, int, int, int], Transition] = {}
        # guards self.doors:
        self.lock3 = RLock()
        self.doors: dict[tuple[str, int, int, int], dict[str, Door]] = {}

        self.load()

    def load(self):
        """Load node data from the database."""
        try:
            db = get_database()
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
                    self.transitions[(area, x, y, z)] = dill.loads(blob)
                except Exception as e:
                    logger.error(f"Error loading transition to {area},{x},{y},{z}: {e}")

            cursor.execute("SELECT area, x, y, z, data FROM doors")
            for area, x, y, z, blob in cursor:
                try:
                    self.doors[(area, x, y, z)] = dill.loads(blob)
                except Exception as e:
                    logger.error(f"Error loading doors at {area},{x},{y},{z}: {e}")

            for area in self.areas.values():
                for grid in area.grids.values():
                    for node in grid.nodes.values():
                        if hasattr(node, "resolve_relations"):
                            node.resolve_relations()

        except Exception as e:
            logger.error(f"Error loading node data from DB: {e}")

    def save(self):
        db = get_database()
        cursor = db.connection.cursor()

        with self.lock:
            areas_snapshot = list(self.areas.values())
        with self.lock2:
            transitions_snapshot = list(self.transitions.values())
        with self.lock3:
            doors_snapshot = list(self.doors.items())

        with db.lock:
            cursor.execute("BEGIN TRANSACTION")
            try:
                for area in areas_snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO areas (name, data) VALUES (?, ?)",
                        (area.name, dill.dumps(area)),
                    )

                for t in transitions_snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO transitions (to_area, to_x, to_y, to_z, data) VALUES (?, ?, ?, ?, ?)",
                        (t.to_coord[0], t.to_coord[1], t.to_coord[2], t.to_coord[3], dill.dumps(t)),
                    )
                for coord, doors_dict in doors_snapshot:
                    cursor.execute(
                        "INSERT OR REPLACE INTO doors (area, x, y, z, data) VALUES (?, ?, ?, ?, ?)",
                        (coord[0], coord[1], coord[2], coord[3], dill.dumps(doors_dict)),
                    )

                cursor.execute("COMMIT")
            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Error saving node data to DB: {e}")

    # def get_objects(self, include_objects=True, include_npcs=False, include_pcs=False):
    #     result = []
    #     with self.lock:
    #         for v in self.areas.values():
    #             o = v.get_objects(include_objects, include_npcs, include_pcs)
    #             if o:
    #                 result.extend(o)
    #     return result

    def get_doors(self, coord: tuple[str, int, int, int]) -> dict[str, Door] | None:
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

    def remove_door(self, door: Door):
        with self.lock3:
            d = self.doors.get(door.from_coord)
            rem_keys = []
            if d:
                for k, v in d:
                    if v == d:
                        rem_keys.append(k)
                for k in rem_keys:
                    del d[k]
            rem_keys.clear()
            d = self.doors.get(door.to_coord)
            if d:
                for k, v in d:
                    if v == d:
                        rem_keys.append(k)
                for k in rem_keys:
                    del d[k]

    def add_node(self, node: Node):
        area = self.get_area(node.coord[0])
        if area:
            grid = area.get_grid(node.coord[3])
            if grid:
                grid.add_node(node)
            else:
                grid = NodeGrid(node.coord[0], node.coord[3])
                grid.add_node(node)
                area.add_grid(grid)
        else:
            area = NodeArea(node.coord[0])
            grid = NodeGrid(node.coord[0], node.coord[3])
            grid.add_node(node)
            area.add_grid(grid)
            self.add_area(area)

    def add_area(self, area: NodeArea):
        with self.lock:
            self.areas[area.name] = area

    def remove_area(self, name: str):
        with self.lock:
            area = self.areas[name]
            area.clear()
            del self.areas[name]

    def clear(self):
        with self.lock:
            for v in self.areas.values():
                v.clear()
            self.areas.clear()
        with self.lock2:
            self.transitions.clear()
        with self.lock3:
            self.doors.clear()

    def get_area(self, name: str) -> NodeArea | None:
        with self.lock:
            return self.areas.get(name)

    def get_areas(self) -> list[NodeArea]:
        with self.lock:
            return [x for x in self.areas.values()]

    def get_node(self, coord: tuple[str, int, int, int]) -> Node | None:
        area = self.get_area(coord[0])
        if area:
            grid = area.get_grid(coord[3])
            if grid:
                return grid.get_node((coord[1], coord[2]))
        return None

    def remove_node(self, coord: tuple[str, int, int, int]):
        area = self.get_area(coord[0])
        if area:
            grid = area.get_grid(coord[3])
            if grid:
                grid.remove_node((coord[1], coord[2]))

    def get_nodes(self, coords: list[tuple[str, int, int, int]]) -> list:
        result = []
        for c in coords:
            n = self.get_node(c)
            if n:
                result.append(n)
        return result

    def add_transition(self, transition: Transition):
        with self.lock2:
            self.transitions[transition.to_coord] = transition  # key = destination

    def remove_transition(self, destination: tuple[str, int, int, int]):
        with self.lock2:
            del self.transitions[destination]

    def find_transitions(
        self, from_z=None, to_z=None, from_area=None, to_area=None
    ) -> list[Transition]:
        result = []
        required_matches = 0
        if from_z:
            required_matches += 1
        if to_z:
            required_matches += 1
        if from_area:
            required_matches += 1
        if to_area:
            required_matches += 1
        with self.lock2:
            for t in self.transitions.values():
                matches = 0
                if from_z and t.from_coord[3] == from_z:
                    matches += 1
                    if matches == required_matches:
                        result.append(t)
                        continue
                if to_z and t.to_coord[3] == to_z:
                    matches += 1
                    if matches == required_matches:
                        result.append(t)
                        continue
                if from_area and t.from_coord[0] == from_area:
                    matches += 1
                    if matches == required_matches:
                        result.append(t)
                        continue
                if to_area and t.to_coord[0] == to_area:
                    matches += 1
                    if matches == required_matches:
                        result.append(t)
        return result
