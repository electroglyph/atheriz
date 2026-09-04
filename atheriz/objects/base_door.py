from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node
    from atheriz.utils import Coord
from atheriz.globals.get import get_node_handler
from atheriz.globals.get import get_map_handler
from atheriz.objects.base_lock import AccessLock
from atheriz.logger import logger
import atheriz.settings as settings
from threading import RLock


class Door(AccessLock):
    def __init__(
        self,
        from_coord: Coord = None,
        from_exit: str = None,
        to_coord: Coord = None,
        to_exit: str = None,
        symbol_coord: tuple[int, int] = None,  # map coord to show the door symbol
        closed_symbol: str = None,
        open_symbol: str = None,
        closed: bool = True,
        locked: bool = False,
    ) -> None:
        self.lock = RLock()
        self.locked = locked
        self.closed = closed
        self.from_coord = from_coord
        self.from_exit = from_exit
        self.to_coord = to_coord
        self.to_exit = to_exit
        self.symbol_coord = symbol_coord
        self.closed_symbol = closed_symbol
        self.open_symbol = open_symbol
        super().__init__()

    def __setstate__(self, state):
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            for cls in type(self).mro():
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            state.pop("lock", None)
            return state

    @classmethod
    def create(
        cls,
        from_coord: Coord,
        from_exit: str,
        to_coord: Coord,
        to_exit: str,
        symbol_coord: tuple[int, int] = None,
        closed_symbol: str = "",
        open_symbol: str = "",
        closed: bool = True,
        locked: bool = False,
    ) -> Door:
        return cls(
            from_coord,
            from_exit,
            to_coord,
            to_exit,
            symbol_coord,
            closed_symbol,
            open_symbol,
            closed,
            locked,
        )

    def __str__(self):
        return (
            f"Door({self.from_coord}, 'from_exit' : {self.from_exit}, 'to_coord' : {self.to_coord}, 'to_exit' :"
            f" {self.to_exit})"
        )

    def desc(self, from_coord: Coord) -> str:
        with self.lock:
            status = "A closed" if self.closed else "An open"
        if from_coord == self.from_coord:
            return f"{status} door leading {self.from_exit}"
        elif from_coord == self.to_coord:
            return f"{status} door leading {self.to_exit}"
        else:
            return "Door desc: unexpected coord."

    def get_nodes(self) -> tuple[Node | None, Node | None]:
        nh = get_node_handler()
        from_node = nh.get_node(self.from_coord)
        to_node = nh.get_node(self.to_coord)
        if not from_node:
            logger.error(f"{str(self)} has from_coord which doesn't resolve to a Node.")
        if not to_node:
            logger.error(f"{str(self)} has to_coord which doesn't resolve to a Node.")
        return from_node, to_node

    def try_open(self, caller: Object) -> bool:
        from_node, to_node = self.get_nodes()
        loc = caller.location
        with self.lock:
            if not self.closed:
                status = "already_open"
            elif self.locked:
                status = "locked"
            elif not self.access(caller, "open"):
                status = "no_access"
            else:
                self.closed = False
                status = "opened"
        if status == "opened":
            try:
                nh = get_node_handler()
                nh.mark_doors_modified()
            except Exception:
                pass
        if status == "already_open":
            if from_node:
                from_node.msg_contents(
                    f"$You(target) $conj(open) the already open door just to be sure.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            if to_node:
                to_node.msg_contents(
                    f"$You(target) $conj(open) the already open door just to be sure.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return True
        if status == "locked":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to open the door, but it won't budge.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        if status == "no_access":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to open the door, but an unknown force prevents it.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        self.map_open()
        if loc:
            loc.msg_contents(
                f"$You(target) $conj(open) the door.",
                mapping={"target": caller},
                from_obj=caller,
            )
        return True

    def try_close(self, caller: Object) -> bool:
        from_node, to_node = self.get_nodes()
        loc = caller.location
        with self.lock:
            if self.closed:
                status = "already_closed"
            elif not self.access(caller, "close"):
                status = "no_access"
            else:
                self.closed = True
                status = "closed"
        if status == "closed":
            try:
                nh = get_node_handler()
                nh.mark_doors_modified()
            except Exception:
                pass
        if status == "already_closed":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to close the door, but it is already closed.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        if status == "no_access":
            if from_node:
                from_node.msg_contents(
                    f"$You(target) $conj(try) to close the door, but an unknown force prevents it.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            if to_node:
                to_node.msg_contents(
                    f"$You(target) $conj(try) to close the door, but an unknown force prevents it.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        self.map_close()
        if from_node:
            from_node.msg_contents(
                f"$You(target) $conj(close) the door.",
                mapping={"target": caller},
                from_obj=caller,
            )
        if to_node:
            to_node.msg_contents(
                f"$You(target) $conj(close) the door.",
                mapping={"target": caller},
                from_obj=caller,
            )
        return True

    def try_lock(self, caller: Object) -> bool:
        loc = caller.location
        with self.lock:
            if not self.access(caller, "lock"):
                status = "no_access"
            elif not self.closed:
                status = "not_closed"
            elif self.locked:
                status = "already_locked"
            else:
                self.locked = True
                status = "locked"
        if status == "locked":
            try:
                nh = get_node_handler()
                nh.mark_doors_modified()
            except Exception:
                pass
        if status == "no_access":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to lock the door, but an unknown force prevents it.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        if status == "not_closed":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to lock the door, but You can't lock an open door.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        if status == "already_locked":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to lock the door, but it is already locked.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        if loc:
            loc.msg_contents(
                f"$You(target) $conj(lock) the door.",
                mapping={"target": caller},
                from_obj=caller,
            )
        return True

    def try_unlock(self, caller: Object) -> bool:
        from_node, to_node = self.get_nodes()
        loc = caller.location
        with self.lock:
            if not self.access(caller, "unlock"):
                status = "no_access"
            elif self.locked:
                self.locked = False
                status = "unlocked"
            else:
                status = "already_unlocked"
        if status == "unlocked":
            try:
                nh = get_node_handler()
                nh.mark_doors_modified()
            except Exception:
                pass
        if status == "no_access":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(try) to unlock the door, but an unknown force prevents it.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return False
        if status == "unlocked":
            if loc:
                loc.msg_contents(
                    f"$You(target) $conj(unlock) the door.",
                    mapping={"target": caller},
                    from_obj=caller,
                )
            return True
        if loc:
            loc.msg_contents(
                f"$You(target) $conj(try) to unlock the door, but it is already unlocked.",
                mapping={"target": caller},
                from_obj=caller,
            )
        return False

    def map_close(self):
        if settings.MAP_ENABLED and self.symbol_coord and self.from_coord and self.to_coord:
            mh = get_map_handler()
            seen = set()
            for coord in (self.from_coord, self.to_coord):
                key = (coord.area, coord.z)
                if key in seen:
                    continue
                seen.add(key)
                mi = mh.get_mapinfo(coord.area, coord.z)
                if mi:
                    with mi.lock:
                        mi.post_grid[self.symbol_coord] = self.closed_symbol
                        if mi.pre_grid:
                            mi.pre_grid[self.symbol_coord] = self.closed_symbol
                            mi.map_changed = True
                    mi.render(True)

    def map_open(self):
        if settings.MAP_ENABLED and self.symbol_coord and self.from_coord and self.to_coord:
            mh = get_map_handler()
            seen = set()
            for coord in (self.from_coord, self.to_coord):
                key = (coord.area, coord.z)
                if key in seen:
                    continue
                seen.add(key)
                mi = mh.get_mapinfo(coord.area, coord.z)
                if mi:
                    with mi.lock:
                        mi.post_grid[self.symbol_coord] = self.open_symbol
                        if mi.pre_grid:
                            mi.pre_grid[self.symbol_coord] = self.open_symbol
                            mi.map_changed = True
                    mi.render(True)
