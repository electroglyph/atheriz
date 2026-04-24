from __future__ import annotations
from typing import Callable
from math import gcd
from atheriz.utils import is_iter, make_iter
from typing import Any, Optional
from atheriz.globals.objects import get
import random
from threading import RLock
from typing import TYPE_CHECKING
from atheriz.utils import (
    wrap_truecolor,
    wrap_xterm256,
)
from atheriz.objects import funcparser
from atheriz.globals.objects import get
from atheriz.objects.contents import search
from atheriz.globals.get import get_node_handler, get_async_ticker, get_map_handler
from atheriz.commands.base_cmdset import CmdSet
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.objects.contents import filter_contents, group_by_name
from atheriz.utils import wrap_truecolor, ensure_thread_safe
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.objects.base_lock import AccessLock
from atheriz.objects.base_flags import Flags

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
        self.aliases = aliases if aliases else []
        self.coord = coord

    def __eq__(self, other):
        if not isinstance(other, NodeLink):
            return False
        return self.name == other.name and self.coord == other.coord

    def __str__(self):
        return f"NodeLink: {self.name}, {self.aliases}, {self.coord}"

    def __getstate__(self):
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)


class Node(Flags, AccessLock):
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

    def at_desc(self, looker: Object | None = None, **kwargs):
        """Called when the node is looked at."""
        pass

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
        links: list[NodeLink] = None,
        tick_seconds: float = settings.DEFAULT_TICK_SECONDS,
    ):
        self.lock = RLock()
        super().__init__()
        self.open_attenuation = settings.DEFAULT_OPEN_SOUND_ATTENUATION
        self.enclosed_attenuation = settings.DEFAULT_ENCLOSED_SOUND_ATTENUATION
        self.ambient_sound_level = settings.DEFAULT_AMBIENT_SOUND_LEVEL
        self.coord = coord
        self.desc = desc
        self._tick_seconds = tick_seconds
        self.theme = theme
        self.symbol = symbol
        self.legend_desc = legend_desc
        self.links = links if links else []
        self._contents = set()
        self.is_node = True
        self.id = -1
        self.nouns = {}
        self.scripts: set[int] = set()
        self.hooks: dict[str, set[Callable]] = {}
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            for cls in type(self).mro():
                # remove excluded keys
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            # Node specific exclusions:
            state.pop("lock", None)
            state.pop("hooks", None)
            return state

    def __setstate__(self, state):
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        if hasattr(self, "_contents") and not isinstance(self._contents, set):
            object.__setattr__(self, "_contents", set(self._contents))
        object.__setattr__(self, "hooks", {})
        # call __setstate__ for all parent classes
        mro = type(self).mro()
        current_idx = next(
            (i for i, c in enumerate(mro) if c.__module__ == "atheriz.objects.nodes" and c.__qualname__ == "Node"),
            len(mro),
        )
        ancestors = mro[current_idx + 1 :]
        for cls in reversed(ancestors):
            if "__setstate__" in cls.__dict__:
                cls.__setstate__(self, state)
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    def resolve_relations(self):
        """
        Called as pass 2 of the database load to reconnect relational IDs to actual objects.
        This reconstitutes pointers and reschedules async ticker events or script hooks
        for the Node.
        """
        if getattr(self, "_is_tickable", False):
            at = get_async_ticker()
            at.add_coro(self.at_tick, self._tick_seconds)
        scripts = getattr(self, "scripts", None)
        if scripts:
            for id in scripts:
                if script := get(id):
                    script[0].install_hooks(self)

        self.at_init()

    @property
    def tick_seconds(self) -> float:
        """float: The interval in seconds at which `at_tick` is called."""
        return self._tick_seconds

    @tick_seconds.setter
    def tick_seconds(self, value):
        if self._is_tickable and value != self._tick_seconds:
            at = get_async_ticker()
            at.remove_coro(self.at_tick, self._tick_seconds)
            at.add_coro(self.at_tick, value)
        self._tick_seconds = value

    @property
    def is_tickable(self) -> bool:
        """bool: Indicates if this node is currently registered with the asynchronous ticker."""
        return self._is_tickable

    @is_tickable.setter
    def is_tickable(self, value):
        self._is_tickable = value
        at = get_async_ticker()
        if value:
            at.add_coro(self.at_tick, self._tick_seconds)
        else:
            at.remove_coro(self.at_tick, self._tick_seconds)

    def at_pre_emit_sound(self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool):
        """
        Optionally modify parameters before the sound is emitted.
        Return False for the first argument to prevent the sound from being emitted.

        Args:
            emitter (Object): The object emitting the sound.
            sound_desc (str): The description of the sound.
            sound_msg (str): The message of the sound.
            loudness (float): The loudness of the sound.
            is_say (bool): Whether the sound is a say.

        Returns:
            tuple[bool, Object, str, str, float, bool]: If first element is False, the sound will not be emitted.
        """
        # this function can modify any of the args before returning them
        return True, emitter, sound_desc, sound_msg, loudness, is_say

    def at_pre_hear(
        self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool
    ) -> tuple[bool, Object, str, str, float, bool]:
        """
        Optionally modify parameters before the sound is heard.
        Return False for the first argument to prevent the sound from being heard.
        However, to prevent sound transmission, you must reduce the loudness

        Args:
            emitter (Object): The object emitting the sound.
            sound_desc (str): The description of the sound.
            sound_msg (str): The message of the sound.
            loud (bool): Whether the sound is loud.
            is_say (bool): Whether the sound is a say.

        Returns:
            tuple[bool, Object, str, str, float, bool]: If first element is False, the sound will not be emitted.
        """
        # this function can modify any of the args before returning them
        return True, emitter, sound_desc, sound_msg, loudness, is_say

    def at_hear(self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool) -> float:
        """
        Args:
            emitter (Object): The object emitting the sound.
            sound_desc (str): The description of the sound.
            sound_msg (str): The message of the sound.
            loudness (float): The loudness of the sound.
            is_say (bool): Whether the sound is a say.

        Returns:
            float: The remaining loudness of the sound.
        """
        allow, emitter, sound_desc, sound_msg, loudness, is_say = self.at_pre_hear(
            emitter, sound_desc, sound_msg, loudness, is_say
        )
        open = False
        ndh = get_node_handler()
        doors = ndh.get_doors(self.coord)
        if doors:
            for door in doors.values():
                if door.open:
                    open = True
                    break
        else:
            open = True
        attenuation = self.open_attenuation if open else self.enclosed_attenuation
        if not allow or loudness <= self.ambient_sound_level:
            return loudness - attenuation
        for o in self.contents:
            if o.can_hear:
                allow, emitter, sound_desc, sound_msg, loudness, is_say = o.at_pre_hear(
                    emitter, sound_desc, sound_msg, loudness, is_say
                )
                if not allow:
                    continue
                o.at_hear(emitter, sound_desc, sound_msg, loudness, is_say)
        return loudness - attenuation

    def at_pre_object_leave(self, destination: Node | Object | None, to_exit: str | None = None, **kwargs) -> bool:
        """
        Called before an object leaves the node. Returning False aborts the move.

        Args:
            destination (Node | Object | None): The destination of the object.
            to_exit (str | None, optional): The exit used to leave.
            **kwargs: Extra arguments.

        Returns:
            bool: True to allow leaving, False to abort.
        """
        return True

    def at_object_leave(self, destination: Node | Object | None, to_exit: str | None = None, **kwargs) -> None:
        """
        Called after an object has successfully left the node.

        Args:
            destination (Node | Object | None): The destination of the object.
            to_exit (str | None, optional): The exit used to leave.
            **kwargs: Extra arguments.
        """
        pass

    def at_pre_object_receive(self, source: Node | Object | None, from_exit: str | None = None, **kwargs) -> bool:
        """
        Called before an object enters the node. Returning False aborts the entry.

        Args:
            source (Node | Object | None): The source location.
            from_exit (str | None, optional): The exit used to enter.
            **kwargs: Extra arguments.

        Returns:
            bool: True to allow entry, False to abort.
        """
        return True

    def at_object_receive(self, source: Node | Object | None, from_exit: str | None = None, **kwargs) -> None:
        """
        Called after an object has successfully entered the node.

        Args:
            source (Node | Object | None): The source location.
            from_exit (str | None, optional): The exit used to enter.
            **kwargs: Extra arguments.
        """
        pass

    def at_init(self):
        """
        Called after this node object is deserialized and all its attributes
        and components are linked and instantiated.
        """
        pass

    def delete(self, caller: Object, recursive: bool = False) -> tuple[int, list] | None:
        """Delete this node.

        Args:
            recursive (bool, optional): Delete all objects in this node. Defaults to False.

        Returns:
            tuple[int, list] | None: (count of nodes deleted/moved, list of object ops), or None if aborted.
        """

        def _delete_recursive(obj: Node) -> list:
            all_ops = []
            if obj.contents:
                for content in list(obj.contents):
                    res = content.delete(caller, True)
                    if res is None:
                        continue
                    all_ops.extend(res)
            return all_ops

        def _move_contents(obj: Node) -> list:
            if obj.contents:
                for content in list(obj.contents):
                    content.move_to(content.home)
            return []

        def _self_delete():
            get_node_handler().remove_node(self.coord)
            self.is_deleted = True

        if not self.at_delete(caller):
            return None

        all_ops = _delete_recursive(self) if recursive else _move_contents(self)
        _self_delete()
        return 0, all_ops

    def at_delete(self, caller: Object) -> bool:
        """
        Called before a node is fundamentally deleted from the world grid.
        Evaluates the node's delete lock.

        Args:
            caller (Object): The object executing the command.

        Returns:
            bool: True to proceed with deletion, False to stop.
        """
        if not self.access(caller, "delete"):
            caller.msg(f"You cannot delete {self.get_display_name(caller)}.")
            logger.info(
                f"{caller.name} ({caller.id}) tried to delete {self.get_display_name(caller)} ({self.id}) but failed."
            )
            return False
        return True

    def add_noun(self, noun: str, desc: str):
        """
        Adds a static scenic noun to the room.

        Args:
            noun (str): The keyword or name to look at.
            desc (str): The description returned when looked at.
        """
        with self.lock:
            self.nouns[noun] = desc

    def remove_noun(self, noun: str):
        """
        Removes a scenic noun from the room.

        Args:
            noun (str): The keyword to remove.
        """
        with self.lock:
            del self.nouns[noun]

    def get_noun(self, noun: str) -> str | None:
        """
        Retrieves the description of a scenic noun.

        Args:
            noun (str): The keyword to look for.

        Returns:
            str | None: The description, or None if not found.
        """
        with self.lock:
            return self.nouns.get(noun)

    def __str__(self):
        return f"Node: {self.coord}"

    def search(self, query: str) -> list[Any]:
        """
        Searches the contents of this node using the given query string.

        Args:
            query (str): The search phrase.

        Returns:
            list[Any]: A list of objects matching the search query.
        """
        return search(self, query)

    def get_links(self) -> list[NodeLink]:
        """
        Retrieves a copy of the links (exits) leading out of this node.

        Returns:
            list[NodeLink]: A list of exit links.
        """
        with self.lock:
            return self.links.copy() if self.links else []

    def has_link_name(self, name: str) -> bool:
        """
        Check if this node has a link with the given name.
        Args:
            name (str): Name of the link to check
        Returns:
            bool: True if the link exists, False otherwise
        """
        with self.lock:
            return any(link.name == name for link in self.links)

    def get_link_by_name(self, name: str) -> NodeLink | None:
        name = name.lower()
        with self.lock:
            for l in self.links:
                if l.name.lower() == name or name in l.aliases:
                    return l

    @property
    def area(self) -> Any:
        """NodeArea | None: The NodeArea object that encompasses this node."""
        nh = get_node_handler()
        return nh.get_area(self.coord[0])

    @property
    def grid(self) -> Any:
        """NodeGrid | None: The NodeGrid object corresponding to this node's Z-level."""
        nh = get_node_handler()
        a = nh.get_area(self.coord[0])
        if a:
            return a.get_grid(self.coord[3])

    @property
    def name(self) -> str:
        """str: The string representation of this node's coordinates."""
        return str(self.coord)

    def add_script(self, script: int | Any):
        """
        Attach a global script hook to this node.

        Args:
            script (int | Any): The ID of the Script, or the Script object itself.
        """
        script = get(script)[0] if isinstance(script, int) else script
        script.install_hooks(self)
        with self.lock:
            self.scripts.add(script.id)
            self.is_modified = True

    def remove_script(self, script: int | Any):
        """
        Remove a global script hook from this node.

        Args:
            script (int | Any): The ID of the Script, or the Script object itself.
        """
        script = get(script)[0] if isinstance(script, int) else script
        script.remove_hooks(self)
        with self.lock:
            self.scripts.discard(script.id)
            self.is_modified = True

    def get_random_link(self) -> NodeLink | None:
        """
        randomly select a NodeLink (exit) from this Node
        Returns:
            NodeLink | None: NodeLink if this Node has any NodeLinks, otherwise None
        """
        with self.lock:
            return random.choice(self.links) if self.links else None

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
        """
        Remove an exit from this node. Also alerts the map handler if it crosses areas.

        Args:
            name (str): The name of the exit to remove.
        """
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
            self.is_modified = True
            for o in objs:
                o.is_modified = True
                self.add_exits(o)

    def add_object(self, obj: Object):
        """
        add object to this node's inventory
        Args:
            obj: object to add
        """
        with self.lock:
            self._contents.add(obj.id)
            obj.is_modified = True
            self.is_modified = True
            self.add_exits(obj)

    def remove_object(self, obj):
        """
        remove object from this node's inventory
        Args:
            obj (Object): object to remove
        """
        with self.lock:
            self._contents.discard(obj.id)
            self.is_modified = True
        obj.internal_cmdset.remove_by_tag("exits")

    # this is mostly from Evennia, see EVENNIA_LICENSE.txt
    def msg_contents(
        self,
        text=None,
        exclude=None,
        from_obj=None,
        mapping=None,
        raise_funcparse_errors=False,
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
        contents = self.contents
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
                    key: (obj.get_display_name(looker=receiver) if hasattr(obj, "get_display_name") else str(obj))
                    for key, obj in mapping.items()
                }
            )
            receiver.msg(text=outmessage, from_obj=from_obj, **outkwargs)

    def get_display_things(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the formatted inventory/contents of strictly inanimate items in this node.

        Args:
            looker (Object | None, optional): The object viewing the room. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The formatted string listing contents, or an empty string.
        """
        things = filter_contents(self, lambda x: x.is_item and x.access(looker, "view"))
        thing_names = group_by_name(things, looker)
        return f"{wrap_xterm256('You see:', fg=15, bold=True)} {thing_names}\n" if thing_names else ""

    def get_display_characters(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the formatted list of other characters currently in this node.

        Args:
            looker (Object | None, optional): The object viewing the room (excluded from output). Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The formatted string listing characters, or an empty string.
        """
        if not looker:
            return ""
        characters = filter_contents(
            self,
            lambda x: ((x.is_pc or x.is_npc) and x != looker and x.access(looker, "view")),
        )
        character_names = group_by_name(characters, looker)
        return f"{wrap_xterm256('Characters:', fg=15, bold=True)} {character_names}\n" if character_names else ""

    def get_display_exits(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the formatted list of available exits from this node.

        Args:
            looker (Object | None, optional): The object viewing the room. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The formatted string listing exits, or an empty string.
        """
        if self.links is None:
            return ""
        exit_names = ""
        with self.lock:
            for x in range(len(self.links)):
                exit_names += self.links[x].name
                if x != len(self.links) - 1:
                    exit_names += ", "
        return f"{wrap_xterm256('Exits:', fg=15, bold=True)} {exit_names}\n" if exit_names != "" else ""

    def get_display_doors(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the formatted list of doors present in this node.

        Args:
            looker (Object | None, optional): The object viewing the room. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The formatted string listing doors, or an empty string.
        """
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

    def get_display_desc(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the main descriptive text for this node.

        Args:
            looker (Object | None, optional): The object viewing the room. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The description text, followed by a newline.
        """
        with self.lock:
            return self.desc + "\n" if self.desc else "You see nothing special.\n"

    def get_display_name(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the name of the node (usually returns empty/none for rooms unless builder).

        Args:
            looker (Object | None, optional): The object viewing the room. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The builder string identifying the coord, or an empty string.
        """
        with self.lock:
            if looker.is_builder:
                return wrap_truecolor(
                    f"({self.coord[0]},{self.coord[1]},{self.coord[2]},{self.coord[3]})\n",
                    fg=170,
                )
        return ""

    def return_appearance(self, looker: Object | None = None, **kwargs) -> str:
        """
        Assembles and formats the complete appearance of this room into a single string.
        Fills the standard appearance_template using the object's helper display methods.

        Args:
            looker (Object | None, optional): The object observing this room. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The fully formatted room output string for rendering.
        """
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


class NodeGrid:
    # args are actually required, this is just to simplify deserialization
    def __init__(self, area: str | None = None, z: int | None = None, data: dict | None = None):
        self.area: str | None = area
        self.z = z
        self.is_modified = True
        self.nodes: dict[tuple[int, int], Node] = {}  # x,y coord: Node
        self.lock = RLock()
        self.data = data if data else {}

    def __str__(self):
        return f"NodeGrid(z = {self.z}, area = {self.area})"

    def __eq__(self, other):
        if not isinstance(other, NodeGrid):
            return False
        return self.area == other.area and self.z == other.z and self.nodes == other.nodes and self.data == other.data

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
            self.is_modified = True
        if node.links:
            nh = get_node_handler()
            for l in node.links:
                if self.area != l.coord[0]:  # does this have an exit leading to a different area?
                    nh.add_transition(Transition(node.coord, l.coord, l.name))

    def remove_node(self, coord: tuple[int, int]):
        with self.lock:
            node = self.nodes.pop(coord, None)
            self.is_modified = True
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
        self.is_modified = True
        self.grids: dict[int, NodeGrid] = {}  # {z: map}
        self.lock = RLock()
        self.data = {}
        self.linked_areas = None  # any yells from this area will be broadcast to these areas

    def __len__(self):
        return len(self.grids)

    def __str__(self):
        return f"Area {self.name}: ".join(f"Grid(z = {k}, len = {len(v)}) " for k, v in self.grids.items())

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

    def get_nodes_in_sphere(
        self, center: tuple[int, int, int], radius: float, ignore_center: bool = False
    ) -> list[Node]:
        cx, cy, cz = center
        r2 = radius * radius
        ri = int(radius)
        result = []
        with self.lock:
            for z in range(cz - ri, cz + ri + 1):
                dz = z - cz
                dz2 = dz * dz
                if dz2 > r2:
                    continue
                g = self.grids.get(z)
                if not g:
                    continue
                max_dxy2 = r2 - dz2
                max_dxy = int(max_dxy2**0.5)
                with g.lock:
                    for x in range(cx - max_dxy, cx + max_dxy + 1):
                        dx2 = (x - cx) ** 2
                        remaining = max_dxy2 - dx2
                        if remaining < 0:
                            continue
                        max_dy = int(remaining**0.5)
                        for y in range(cy - max_dy, cy + max_dy + 1):
                            if ignore_center and x == cx and y == cy and z == cz:
                                continue
                            n = g.nodes.get((x, y))
                            if n:
                                result.append(n)
        return result

    def get_rays_in_sphere(
        self, center: tuple[int, int, int], radius: float, ignore_center: bool = True
    ) -> list[list[Node]]:
        nodes = self.get_nodes_in_sphere(center, radius, ignore_center)
        cx, cy, cz = center
        rays: dict[tuple[int, int, int], list[tuple[int, Node]]] = {}
        for n in nodes:
            nx, ny, nz = n.coord[1], n.coord[2], n.coord[3]
            dx, dy, dz = nx - cx, ny - cy, nz - cz
            g = gcd(gcd(abs(dx), abs(dy)), abs(dz))
            direction = (dx // g, dy // g, dz // g)
            dist_sq = dx * dx + dy * dy + dz * dz
            bucket = rays.get(direction)
            if bucket is None:
                rays[direction] = [(dist_sq, n)]
            else:
                bucket.append((dist_sq, n))
        result = []
        for bucket in rays.values():
            bucket.sort()
            result.append([n for _, n in bucket])
        return result

    def get_neighbors(self, coord: tuple[int, int, int]) -> list[Node]:
        x, y, z = coord
        neighbors = []
        with self.lock:
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                g = self.grids.get(z + dz)
                if g:
                    n = g.nodes.get((x + dx, y + dy))
                    if n:
                        neighbors.append(n)
        return neighbors

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
            self.is_modified = True

    def get_grid(self, z: int) -> NodeGrid | None:
        with self.lock:
            return self.grids.get(z)

    def remove_grid(self, z: int):
        with self.lock:
            m = self.grids[z]
            m.clear()
            del self.grids[z]
            self.is_modified = True

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
