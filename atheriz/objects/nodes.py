from typing import Callable
from atheriz.utils import is_iter, make_iter, iter_to_str
from typing import Any, Iterable, Optional
from atheriz.singletons.objects import get
import random
from threading import Lock, RLock
from typing import TYPE_CHECKING
from pyatomix import AtomicFlag, AtomicInt
from atheriz.utils import (
    wrap_truecolor,
    get_import_path,
    instance_from_string,
    wrap_xterm256,
    tuple_to_str,
    str_to_tuple,
)
from atheriz.objects import funcparser
from atheriz.singletons.objects import get, filter_by
from atheriz.objects.contents import search
from atheriz.singletons.get import get_node_handler, get_async_ticker
from atheriz.commands.base_cmdset import CmdSet
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.objects.contents import filter_contents, group_by_name
from atheriz.utils import wrap_truecolor
from atheriz.logger import logger
import atheriz.settings as settings
import dill
import base64

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

_MSG_CONTENTS_PARSER = funcparser.FuncParser(funcparser.ACTOR_STANCE_CALLABLES)

appearance_template = """{name}{desc}{doors}{exits}{characters}{things}"""


class NodeLink:
    """
    this is the equivalent to an exit
    """

    # name and coord are actually required, but we're making them optional to simplify deserialization
    def __init__(
        self,
        name: str = None,
        coord: tuple[str, int, int, int] = None,
        aliases: Optional[list[str]] = None,
    ):
        """
        Args:
            name (str): name of the exit, i.e. North (this will be added to object's cmdset on entering the room)
            coord (tuple[str,int,int,int]): coord this exit leads to (area,x,y,z)
            aliases (list[str] | None, optional): exit aliases, i.e. 'n' (these will be added to object's cmdset on entering the room). Defaults to None.
        """
        self.name = name
        self.aliases = aliases
        self.coord = coord

    def __eq__(self, other):
        if not isinstance(other, NodeLink):
            return False
        return self.name == other.name and self.coord == other.coord

    def __str__(self):
        return f"NodeLink: {self.name}, {self.aliases}, {self.coord}"

    def __getstate__(self):
        state = self.__dict__.copy()
        state["__import_path__"] = get_import_path(self)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)


class Node:
    """
    this is the equivalent to a room.
    many of the functions below are inspired heavily by or pulled straight from evennia.objects.objects.DefaultObject.
    """

    def __eq__(self, other):
        if isinstance(other, Node):
            return self.coord == other.coord
        return False

    def __ne__(self, other):
        if isinstance(other, Node):
            return self.coord != other.coord
        return True

    is_node = True
    is_pc = False
    is_item = False
    is_connected = False
    is_npc = False
    is_mapable = False
    is_container = False
    is_channel = False
    is_account = False
    home = None

    def at_desc(self, *args, **kwargs):
        return self.desc

    def at_tick(self):
        """
        Called every tick.
        """
        pass

    @property
    def contents(self) -> list[Object]:
        with self.lock:
            return get(self._contents)

    def for_contents(self, func, exclude=None, **kwargs):
        contents = self.contents
        if exclude:
            exclude = make_iter(exclude)
            contents = [obj for obj in contents if obj not in exclude]
        for obj in contents:
            func(obj, **kwargs)

    # coord is actually required, this is just to simplify deserialization
    def __init__(
        self,
        coord: tuple[str, int, int, int] = None,
        desc: str = None,
        theme: str = None,
        symbol: str = None,
        legend_desc: str = None,
        data: dict = None,
        links: list[NodeLink] = None,
        tick_seconds: float = settings.DEFAULT_TICK_SECONDS,
    ):
        self.coord = coord
        self.desc = desc
        self._is_tickable = False
        self._tick_seconds = tick_seconds
        self.theme = theme
        self.symbol = symbol
        self.legend_desc = legend_desc
        self.data = data if data else {}
        self.links = links
        self._contents = set()
        self.lock = RLock()
        self.is_deleted = False
        self.nouns = {}
        self.locks: dict[str, list[Callable]] = {}
        if settings.SLOW_LOCKS:
            self.access = self._safe_access
        else:
            self.access = self._fast_access

    def _safe_access(self, accessing_obj: Object, name: str):
        if accessing_obj.is_superuser:
            return True
        with self.lock:
            lock_list = self.locks.get(name, [])
            for lock in lock_list:
                if not lock(accessing_obj):
                    return False
            return True

    def _fast_access(self, accessing_obj: Object, name: str):
        if accessing_obj.is_superuser:
            return True
        lock_list = self.locks.get(name, [])
        for lock in lock_list:
            if not lock(accessing_obj):
                return False
        return True

    def add_lock(self, lock_name: str, callable: Callable):
        """
        Add a lock to this object.

        For example:
        ```python
        obj.add_lock("control", lambda x: x.is_builder)
        ```

        Args:
            lock_name (str): The name of the lock to add.
            callable (Callable): The callable to add to the lock.
        """
        with self.lock:
            l = self.locks.get(lock_name, [])
            l.append(callable)
            self.locks[lock_name] = l

    def clear_locks_by_name(self, lock_name: str):
        """
        Clear all locks by name.

        Args:
            lock_name (str): The name of the lock to clear.
        """
        with self.lock:
            self.locks.pop(lock_name, None)

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            state.pop("access", None)
            return state

    def __setstate__(self, state):
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        if hasattr(self, "_contents") and not isinstance(self._contents, set):
            object.__setattr__(self, "_contents", set(self._contents))
        if settings.SLOW_LOCKS:
            object.__setattr__(self, "access", self._safe_access)
        else:
            object.__setattr__(self, "access", self._fast_access)
        if self._is_tickable:
            at = get_async_ticker()
            at.add_coro(self.at_tick, self._tick_seconds)
        self.at_init()

    @property
    def tick_seconds(self):
        return self._tick_seconds

    @tick_seconds.setter
    def tick_seconds(self, value):
        if self._is_tickable and value != self._tick_seconds:
            at = get_async_ticker()
            at.remove_coro(self.at_tick, self._tick_seconds)
            at.add_coro(self.at_tick, value)
        self._tick_seconds = value

    @property
    def is_tickable(self):
        return self._is_tickable

    @is_tickable.setter
    def is_tickable(self, value):
        self._is_tickable = value
        at = get_async_ticker()
        if value:
            at.add_coro(self.at_tick, self._tick_seconds)
        else:
            at.remove_coro(self.at_tick, self._tick_seconds)

    def set_data(self, key, value):
        """save arbitrary data for this node... make sure it can be pickled"""
        with self.lock:
            self.data[key] = value

    def get_data(self, key):
        """load arbitrary data for this node... make sure it can be pickled"""
        with self.lock:
            return self.data.get(key)

    def remove_data(self, key):
        with self.lock:
            del self.data[key]

    # def pre_emit_sound(
    #     self, emitter: Object, sound_desc: str, sound_msg: str, loud: bool, is_say: bool
    # ) -> tuple:
    #     """set sound_msg to '' to cancel sound propagation"""
    #     return emitter, sound_desc, sound_msg, loud, is_say

    # def at_hear(self, emitter: Object, sound_desc: str, sound_msg: str, loud: bool, is_say: bool):
    #     emitter, sound_desc, sound_msg, loud, is_say = self.pre_emit_sound(
    #         emitter, sound_desc, sound_msg, loud, is_say
    #     )
    #     if not sound_msg:
    #         return
    #     objs = self.get_objects(True, True, True)
    #     for o in objs:
    #         if o.can_hear:
    #             o.at_hear(emitter, sound_desc, sound_msg, loud, is_say)

    # def get_objects(
    #     self, include_objects=True, include_npcs=False, include_pcs=False
    # ) -> list[Object]:
    #     if not self._contents:
    #         return []
    #     result = []
    #     with self.lock:
    #         for o in self.contents:
    #             if (
    #                 (include_objects and o.is_object)
    #                 or (include_npcs and o.is_npc)
    #                 or (include_pcs and o.is_pc)
    #             ):
    #                 # result.append((o, self))
    #                 result.append(o)
    #     return result

    def at_init(self):
        """
        Called after this object is deserialized and all attributes are set.
        """
        pass

    def delete(self, caller: Object, recursive: bool = False) -> int:
        """Delete this node.

        Args:
            recursive (bool, optional): Delete all objects in this node. Defaults to False.

        Returns:
            int: Number of objects deleted, not including the Node itself.
        """

        def _delete_recursive(obj: Node) -> int:
            count = 0
            if obj.contents:
                for content in list(obj.contents):
                    count += content.delete(caller, True)
            return count

        def _move_contents(obj: Node) -> int:
            count = 0
            if obj.contents:
                for content in list(obj.contents):
                    content.move_to(content.home)
                    count += 1
            return count

        def _self_delete():
            get_node_handler().remove_node(self.coord)
            self.is_deleted = True

        if not self.at_delete(caller):
            _self_delete()
            return 0
        
        count = _delete_recursive(self) if recursive else _move_contents(self)
        _self_delete()
        return count

    def at_delete(self, caller: Object) -> bool:
        """
        Called before this object is deleted.
        Return False to cancel deletion.
        """
        return True

    def add_noun(self, noun: str, desc: str):
        with self.lock:
            self.nouns[noun] = desc

    def remove_noun(self, noun: str):
        with self.lock:
            del self.nouns[noun]

    def get_noun(self, noun: str):
        with self.lock:
            return self.nouns.get(noun)

    def __str__(self):
        return f"Node: {self.coord}"

    def search(self, query: str) -> list[Any]:
        return search(self, query)

    @property
    def area(self):
        nh = get_node_handler()
        return nh.get_area(self.coord[0])

    @property
    def grid(self):
        nh = get_node_handler()
        a = nh.get_area(self.coord[0])
        if a:
            return a.get_grid(self.coord[3])

    @property
    def name(self):
        return str(self.coord)

    def get_random_link(self) -> NodeLink | None:
        """
        randomly select a NodeLink (exit) from this Node
        Returns:
            NodeLink | None: NodeLink if this Node has any NodeLinks, otherwise None
        """
        if self.links:
            return random.choice(self.links)
        return None

    def add_link(self, link: NodeLink):
        """
        add an exit to this node
        Args:
            link (NodeLink): exit to add
        """
        with self.lock:
            if self.links and link not in self.links:
                self.links.append(link)
            elif not self.links:
                self.links = [link]
            for o in self.contents:
                self.add_exits(o)

            if link.coord[0] != self.coord[0]:
                nh = get_node_handler()
                nh.add_transition(Transition(self.coord, link.coord, link.name))

    def remove_link(self, name: str):
        found = None
        index = -1
        with self.lock:
            if self.links:
                for x in range(len(self.links)):
                    if self.links[x].name == name:
                        index = x
                        break
                if index != -1:
                    found = self.links.pop(index)
        if found:
            if self.coord[0] != found.coord[0]:  # need to remove a transition too
                nh = get_node_handler()
                nh.remove_transition(found.coord)

    def add_exits(self, obj: Object, internal: bool = False):
        """
        add this node's exits to obj's cmdset

        Args:
            obj (DefaultObject): object, character, etc. to add exit commands to
        """
        obj.internal_cmdset.remove_by_tag("exits")
        links = object.__getattribute__(self, "links") if internal else self.links
        if links:
            cmds = []
            for n in links:
                ec = ExitCommand()
                ec.key = n.name
                ec.caller_id = obj.id
                ec.location = self.coord
                ec.destination = n.coord
                ec.name = n.name
                ec.aliases = n.aliases
                ec.tag = "exits"
                cmds.append(ec)
            obj.internal_cmdset.adds(cmds)

    def add_objects(self, objs: list[Object]):
        """
        add objects to this node's inventory
        Args:
            objs (list): list of objects to add
        """
        with self.lock:
            self._contents.update([obj.id for obj in objs])
            for o in objs:
                self.add_exits(o)

    def add_object(self, obj: Object):
        """
        add object to this node's inventory
        Args:
            obj: object to add
        """
        with self.lock:
            self._contents.add(obj.id)
            self.add_exits(obj)

    def remove_object(self, obj):
        """
        remove object from this node's inventory
        Args:
            obj (Object): object to remove
        """
        with self.lock:
            self._contents.discard(obj.id)
        obj.internal_cmdset.remove_by_tag("exits")

    # this is mostly from Evennia, see EVENNIA_LICENSE.txt
    def msg_contents(
        self,
        text=None,
        exclude=None,
        from_obj=None,
        mapping=None,
        raise_funcparse_errors=False,
        internal: bool = False,
        **kwargs,
    ):
        """send a message to all objects in this node

        Args:
            text (str | tuple, optional): message to send. Defaults to None.
            exclude (list, optional): objects to exclude from message. Defaults to None.
            from_obj (Object, optional): object sending message. Defaults to None.
            mapping (dict, optional): mapping for funcparse. Defaults to None.
            raise_funcparse_errors (bool, optional): raise funcparse errors. Defaults to False.
            internal (bool, optional): internal message, bypass lock if True. Defaults to False.
            **kwargs: additional keyword arguments to pass to msg
        """
        is_outcmd = text and is_iter(text)
        inmessage = text[0] if is_outcmd else text
        outkwargs = text[1] if is_outcmd and len(text) > 1 else {}
        mapping = mapping or {}
        you = from_obj or self

        if "you" not in mapping:
            mapping["you"] = you
        contents = get(self._contents) if internal else self.contents
        if exclude:
            exclude = make_iter(exclude)
            contents = [obj for obj in contents if obj not in exclude]

        for receiver in contents:
            # actor-stance replacements
            outmessage = _MSG_CONTENTS_PARSER.parse(
                inmessage,
                raise_errors=raise_funcparse_errors,
                return_string=True,
                caller=you,
                receiver=receiver,
                mapping=mapping,
            )
            outmessage = outmessage.format_map(
                {
                    key: (
                        obj.get_display_name(looker=receiver)
                        if hasattr(obj, "get_display_name")
                        else str(obj)
                    )
                    for key, obj in mapping.items()
                }
            )
            receiver.msg(text=(outmessage, outkwargs), from_obj=from_obj, **kwargs)

    def get_display_things(self, looker, **kwargs):
        things = filter_contents(self, lambda x: x.is_item)
        thing_names = group_by_name(things, looker)
        return (
            f"{wrap_xterm256('You see:', fg=15, bold=True)} {thing_names}\n" if thing_names else ""
        )

    def get_display_characters(self, looker, **kwargs):
        characters = filter_contents(self, lambda x: (x.is_pc or x.is_npc) and x != looker)
        character_names = group_by_name(characters, looker)
        return (
            f"{wrap_xterm256('Characters:', fg=15, bold=True)} {character_names}\n"
            if character_names
            else ""
        )

    def get_display_exits(self, looker, **kwargs):
        if self.links is None:
            return ""
        exit_names = ""
        with self.lock:
            for x in range(len(self.links)):
                exit_names += self.links[x].name
                if x != len(self.links) - 1:
                    exit_names += ", "
        return (
            f"{wrap_xterm256('Exits:', fg=15, bold=True)} {exit_names}\n"
            if exit_names != ""
            else ""
        )

    def get_display_doors(self, looker, **kwargs) -> str:
        result = f"{wrap_xterm256('Doors:', fg=15, bold=True)} "
        nh = get_node_handler()
        d = nh.get_doors(self.coord)
        index = 0
        if d:
            for v in d.values():
                if index == 0:
                    result += v.desc(self.coord)
                else:
                    result += v.desc(self.coord).lower()
                if index != len(d) - 1:
                    result += ", "
                index += 1
            return result + "\n"
        else:
            return ""

    def get_display_desc(self, looker, **kwargs):
        with self.lock:
            return self.desc + "\n" if self.desc else "You see nothing special.\n"

    def get_display_name(self, looker: Object | None = None, **kwargs):
        with self.lock:
            if looker.is_builder:
                return wrap_truecolor(
                    f"({self.coord[0]},{self.coord[1]},{self.coord[2]},{self.coord[3]})\n", fg=170
                )
        return ""

    def return_appearance(self, looker, **kwargs):
        if not looker:
            return "You see nothing here."
        return appearance_template.format(
            name=self.get_display_name(looker, **kwargs),
            desc=self.get_display_desc(looker, **kwargs),
            exits=self.get_display_exits(looker, **kwargs),
            characters=self.get_display_characters(looker, **kwargs),
            things=self.get_display_things(looker, **kwargs),
            doors=self.get_display_doors(looker, **kwargs),
        )


def _tuple_to_str(t: tuple) -> str:
    return repr(t)


def _str_to_tuple(s: str) -> tuple:
    import ast

    return ast.literal_eval(s)


class NodeGrid:
    # args are actually required, this is just to simplify deserialization
    def __init__(self, area: str | None = None, z: int | None = None, data: dict | None = None):
        self.area: str | None = area
        self.z = z
        self.nodes: dict[tuple[int, int], Node] = {}  # x,y coord: Node
        self.lock = RLock()
        self.data = data if data else {}

    def __str__(self):
        return f"NodeGrid(z = {self.z}, area = {self.area})"

    def __eq__(self, other):
        if not isinstance(other, NodeGrid):
            return False
        return (
            self.area == other.area
            and self.z == other.z
            and self.nodes == other.nodes
            and self.data == other.data
        )

    def __len__(self):
        return len(self.nodes)

    def set_data(self, key, value):
        """save arbitrary data for this grid... make sure it can be pickled"""
        with self.lock:
            self.data[key] = value

    def get_data(self, key):
        """load arbitrary data for this grid... make sure it can be pickled"""
        with self.lock:
            return self.data.get(key)

    def filter_contents(self, l: Callable[[Any], bool]) -> list[Any]:
        results = []
        with self.lock:
            for v in self.nodes.values():
                results.extend(filter_contents(v, l))
        return results

    def get_random_node(self):
        with self.lock:
            key = random.choice(list(self.nodes.keys()))
            return self.nodes[key]

    def add_node(self, node: Node):
        with self.lock:
            self.nodes[(node.coord[1], node.coord[2])] = node
        if node.links:
            nh = get_node_handler()
            for l in node.links:
                if self.area != l.coord[0]:  # does this have an exit leading to a different area?
                    nh.add_transition(Transition(node.coord, l.coord, l.name))

    def remove_node(self, coord: tuple[int, int]):
        with self.lock:
            node = self.nodes.pop(coord, None)
        if node:
            if node.links:
                nh = get_node_handler()
                for l in node.links:
                    if self.area != l.coord[0]:  # need to remove a transition too
                        nh.remove_transition(l.coord)

    def get_node(self, coord: tuple[int, int]) -> Node | None:
        with self.lock:
            return self.nodes.get(coord)

    def clear(self):
        with self.lock:
            self.nodes.clear()

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()


class NodeArea:
    # name actually IS required, this is just to simplify deserialization
    def __init__(self, name: str = None, theme: str = None):
        self.name = name
        self.theme = theme
        self.grids: dict[int, NodeGrid] = {}  # {z: map}
        self.lock = RLock()
        self.data = {}
        self.linked_areas = None  # any yells from this area will be broadcast to these areas

    def __len__(self):
        return len(self.grids)

    def __str__(self):
        return f"Area {self.name}: ".join(
            f"Grid(z = {k}, len = {len(v)}) " for k, v in self.grids.items()
        )

    def __eq__(self, other):
        if not isinstance(other, NodeArea):
            return False
        return (
            self.name == other.name
            and self.theme == other.theme
            and self.grids == other.grids
            and self.data == other.data
            and self.linked_areas == other.linked_areas
        )

    def get_nodes(self, coords: list[tuple[int, int, int]]) -> list[Node]:
        """optimized for getting nodes from list of coords"""
        result = []
        with self.lock:
            for c in coords:
                g = self.grids.get(c[2])
                if g:
                    with g.lock:
                        n = g.nodes.get((c[0], c[1]))
                    if n:
                        result.append(n)
        return result

    def set_data(self, key, value):
        """save arbitrary data for this area... make sure it can be pickled"""
        with self.lock:
            self.data[key] = value

    def get_data(self, key):
        """load arbitrary data for this node... make sure it can be pickled"""
        with self.lock:
            return self.data.get(key)

    def remove_data(self, key):
        with self.lock:
            del self.data[key]

    # def get_objects(
    #     self,
    #     include_objects=True,
    #     include_npcs=False,
    #     include_pcs=False,
    #     include_linked_areas=False,
    # ):
    #     result = []
    #     with self.lock:
    #         for v in self.grids.values():
    #             o = v.get_objects(include_objects, include_npcs, include_pcs)
    #             if o:
    #                 result.extend(o)
    #         if include_linked_areas:
    #             if self.linked_areas:
    #                 nh = get_node_handler()
    #                 for a in self.linked_areas:
    #                     area = nh.get_area(a)
    #                     if area:
    #                         o = area.get_objects(include_objects, include_npcs, include_pcs, True)
    #                         if o:
    #                             result.extend(o)
    #     return result

    def remove_linked_area(self, area: str):
        with self.lock:
            if self.linked_areas:
                try:
                    self.linked_areas.remove(area)
                except:
                    pass
        nh = get_node_handler()
        a = nh.get_area(area)
        if a:
            a.remove_linked_area(self.name)

    def add_linked_area(self, area: str):
        with self.lock:
            if not self.linked_areas:
                self.linked_areas = {area}
            else:
                self.linked_areas.add(area)
        nh = get_node_handler()
        a = nh.get_area(area)
        if a:
            a.add_linked_area(self.name)

    def add_grid(self, grid: NodeGrid):
        grid.area = self.name
        with self.lock:
            self.grids[grid.z] = grid

    def get_grid(self, z: int) -> NodeGrid | None:
        with self.lock:
            return self.grids.get(z)

    def remove_grid(self, z: int):
        with self.lock:
            m = self.grids[z]
            m.clear()
            del self.grids[z]

    def clear(self):
        with self.lock:
            for v in self.grids.values():
                v.clear()
            self.grids.clear()

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()


class Transition:
    # these are all actually required, this is just to simplify deserialization
    def __init__(
        self,
        from_coord: tuple[str, int, int, int] = None,
        to_coord: tuple[str, int, int, int] = None,
        from_link: str = None,
    ):
        self.from_coord = from_coord
        self.to_coord = to_coord
        self.from_link = from_link  # exit name
        self.lock = RLock()

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()


class Door:
    def __init__(
        self,
        from_coord: tuple[str, int, int, int] = None,
        from_exit: str = None,
        to_coord: tuple[str, int, int, int] = None,
        to_exit: str = None,
        from_symbol_coord: tuple[int, int] = None,  # map coord to show the door symbol
        to_symbol_coord: tuple[int, int] = None,  # map coord to show the door symbol
        closed_symbol: str = None,
        open_symbol: str = None,
        closed: bool = True,
        locked: bool = False,
    ) -> None:
        if locked:
            self.locked = AtomicFlag(True)
        else:
            self.locked = AtomicFlag()
        if closed:
            self.closed = AtomicFlag(True)
        else:
            self.closed = AtomicFlag()
        self.code = random.randint(0, 99)
        self.from_coord = from_coord
        self.from_exit = from_exit
        self.to_coord = to_coord
        self.to_exit = to_exit
        self.from_symbol_coord = from_symbol_coord
        self.to_symbol_coord = to_symbol_coord
        self.closed_symbol = closed_symbol
        self.open_symbol = open_symbol
        self.max_hp = AtomicInt(100)
        self.hp = AtomicInt(100)

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.locked = AtomicFlag(state["locked"])
        self.closed = AtomicFlag(state["closed"])
        self.hp = AtomicInt(state["hp"])
        self.max_hp = AtomicInt(state["max_hp"])

    def __getstate__(self):
        state = self.__dict__.copy()
        state["closed"] = self.closed.test()
        state["locked"] = self.locked.test()
        state["hp"] = self.hp.load()
        state["max_hp"] = self.max_hp.load()
        return state

    def __str__(self):
        return (
            f"Door({self.from_coord}, 'from_exit' : {self.from_exit}, 'to_coord' : {self.to_coord}, 'to_exit' :"
            f" {self.to_exit})"
        )

    def desc(self, from_coord: tuple[str, int, int, int]) -> str:
        status = "A closed" if self.closed.test() else "An open"
        if from_coord == self.from_coord:
            return f"{status} door leading {self.from_exit}"
        elif from_coord == self.to_coord:
            return f"{status} door leading {self.to_exit}"
        else:
            return "Door desc: unexpected coord."

    def full_desc(self, from_coord: tuple[str, int, int, int]) -> str:
        condition = ""
        c = (self.hp.load() / self.max_hp.load()) * 100
        if self.hp.load() == 0:
            condition = "This door is destroyed"
        elif c < 10:
            condition = "This door is in very bad shape"
        elif c < 30:
            condition = "This door is in bad shape"
        elif c < 50:
            condition = "This door is a bit worse for wear"
        elif c < 70:
            condition = "This door is in fair condition"
        elif c < 90:
            condition = "This door has been banged around a bit"
        elif c <= 99:
            condition = "This door has a few scuffs and scratches"
        elif self.hp.load() == self.max_hp.load():
            condition = "This door is in perfect condition"
        status = "A closed" if self.closed.test() else "An open"
        if from_coord == self.from_coord:
            return f"{status} door leading {self.from_exit}\n{wrap_xterm256('Condition', fg=15)}: {condition} ({c:.0f}%)"
        elif from_coord == self.to_coord:
            return f"{status} door leading {self.to_exit}\n{wrap_xterm256('Condition', fg=15)}: {condition} ({c:.0f}%)"
        else:
            return "Door desc: unexpected coord."

    # def map_close(self):
    #     if self.from_symbol_coord:
    #         mh = get_map_handler()
    #         mi = mh.get_mapinfo(self.from_coord[0], self.from_coord[3])
    #         if mi:
    #             mi.update_map(self.from_symbol_coord, self.closed_symbol)
    #     if self.to_symbol_coord:
    #         mh = get_map_handler()
    #         mi = mh.get_mapinfo(self.to_coord[0], self.to_coord[3])
    #         if mi:
    #             mi.update_map(self.to_symbol_coord, self.closed_symbol)

    # def map_open(self):
    #     if self.from_symbol_coord:
    #         mh = get_map_handler()
    #         mi = mh.get_mapinfo(self.from_coord[0], self.from_coord[3])
    #         if mi:
    #             mi.update_map(self.from_symbol_coord, self.open_symbol)
    #     if self.to_symbol_coord:
    #         mh = get_map_handler()
    #         mi = mh.get_mapinfo(self.to_coord[0], self.to_coord[3])
    #         if mi:
    #             mi.update_map(self.to_symbol_coord, self.open_symbol)

    def try_open(self, codes: list[int] | None = None) -> bool:
        if self.locked.test() and codes and self.code in codes:
            self.locked.clear()
            self.closed.clear()
            self.map_open()
            return True
        if not self.locked.test() and self.closed.test():
            self.closed.clear()
            self.map_open()
            return True
        if not self.locked.test() and not self.closed.test():
            return True
        return False

    @property
    def is_closed(self):
        return self.closed.test()

    @property
    def is_locked(self):
        return self.locked.test()

    def open(self):
        self.closed.clear()
        self.map_open()

    def close(self):
        self.closed.test_and_set()
        self.map_close()

    def unlock(self):
        self.locked.clear()

    def lock(self):
        if not self.closed.test():
            self.close()
        self.locked.test_and_set()
