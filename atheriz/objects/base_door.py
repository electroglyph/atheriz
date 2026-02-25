from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node
from atheriz.singletons.get import get_node_handler
from atheriz.singletons.get import get_map_handler
from atheriz.objects.base_lock import AccessLock
from atheriz.logger import logger
from threading import RLock

class Door(AccessLock):
    def __init__(
        self,
        from_coord: tuple[str, int, int, int] = None,
        from_exit: str = None,
        to_coord: tuple[str, int, int, int] = None,
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

    def __setstate__(self, state):
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            return state

    def __str__(self):
        return (
            f"Door({self.from_coord}, 'from_exit' : {self.from_exit}, 'to_coord' : {self.to_coord}, 'to_exit' :"
            f" {self.to_exit})"
        )

    def desc(self, from_coord: tuple[str, int, int, int]) -> str:
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
        with self.lock:
            if not self.closed:
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
            if self.locked:
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(try) to open the door, but it won't budge.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(try) to open the door, but it won't budge.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                return False
            if not self.access(caller, "open"):
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(try) to open the door, but an unknown force prevents it.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(try) to open the door, but an unknown force prevents it.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                return False
            if self.closed:
                self.closed = False
                self.map_open()
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(open) the door.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(open) the door.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )

            return True

    def try_close(self, caller: Object) -> bool:
        from_node, to_node = self.get_nodes()
        with self.lock:
            if self.locked:
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(try) to close the door, but it won't budge.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(try) to close the door, but it won't budge.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                return False
            if not self.access(caller, "close"):
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
            if not self.closed:
                self.closed = True
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
        from_node, to_node = self.get_nodes()
        with self.lock:
            if not self.access(caller, "lock"):
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(try) to lock the door, but an unknown force prevents it.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(try) to lock the door, but an unknown force prevents it.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                return False
            if not self.locked:
                self.locked = True
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(lock) the door.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(lock) the door.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
            return True

    def try_unlock(self, caller: Object) -> bool:
        from_node, to_node = self.get_nodes()
        with self.lock:
            if not self.access(caller, "unlock"):
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(try) to unlock the door, but an unknown force prevents it.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(try) to unlock the door, but an unknown force prevents it.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                return False
            if self.locked:
                self.locked = False
                if from_node:
                    from_node.msg_contents(
                        f"$You(target) $conj(unlock) the door.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
                if to_node:
                    to_node.msg_contents(
                        f"$You(target) $conj(unlock) the door.",
                        mapping={"target": caller},
                        from_obj=caller,
                    )
            return True

    def map_close(self):
        if self.symbol_coord:
            mh = get_map_handler()
            mi = mh.get_mapinfo(self.from_coord[0], self.from_coord[3])
            if mi:
                mi.update_grid(self.symbol_coord, self.closed_symbol)

    def map_open(self):
        if self.symbol_coord:
            mh = get_map_handler()
            mi = mh.get_mapinfo(self.to_coord[0], self.to_coord[3])
            if mi:
                mi.update_grid(self.symbol_coord, self.open_symbol)
