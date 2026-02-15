from typing import Any, Iterable, Optional
from threading import Lock, RLock
from typing import TYPE_CHECKING
from atheriz.utils import tuple_to_str, str_to_tuple
from atheriz.logger import logger
import json
import dill
from pathlib import Path
from atheriz import settings
from atheriz.objects.persist import instance_from_string
from atheriz.objects.nodes import Node, NodeArea, NodeGrid

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import NodeLink, Door, Transition
from time import sleep

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
        # self.areas = _load_areas()
        # self.transitions = _load_transitions()
        # self.doors = _load_doors()
        self.areas = {}
        self.transitions = {}
        self.doors = {}
        ap = Path(settings.SAVE_PATH) / "areas"
        if ap.exists():
            with ap.open("rb") as f:
                self.areas = dill.load(f)
        pt = Path(settings.SAVE_PATH) / "transitions"
        if pt.exists():
            with pt.open("rb") as f:
                self.transitions = dill.load(f)
        pd = Path(settings.SAVE_PATH) / "doors"
        if pd.exists():
            with pd.open("rb") as f:
                self.doors = dill.load(f)

    def save(self):
        save_path = Path(settings.SAVE_PATH)
        save_path.mkdir(parents=True, exist_ok=True)

        def _atomic_save(data, filename, lock):
            path = save_path / filename
            temp_path = path.with_suffix(path.suffix + ".tmp")
            with lock:
                try:
                    with temp_path.open("wb") as f:
                        dill.dump(data, f)
                    temp_path.replace(path)
                except Exception as e:
                    logger.error(f"Error saving {filename}: {e}")
                    if temp_path.exists():
                        temp_path.unlink()

        _atomic_save(self.areas, "areas", self.lock)
        _atomic_save(self.transitions, "transitions", self.lock2)
        _atomic_save(self.doors, "doors", self.lock3)


    # def save(self):
    #     with self.lock:
    #         _save_areas(self.areas)
    #     with self.lock2:
    #         _save_transitions(self.transitions)
    #     with self.lock3:
    #         _save_doors(self.doors)

    def get_objects(self, include_objects=True, include_npcs=False, include_pcs=False):
        result = []
        with self.lock:
            for v in self.areas.values():
                o = v.get_objects(include_objects, include_npcs, include_pcs)
                if o:
                    result.extend(o)
        return result

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
