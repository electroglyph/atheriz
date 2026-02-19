from atheriz.singletons.objects import save_objects
from atheriz.utils import compress_whitespace
from typing import Callable
from atheriz.singletons.objects import get, add_object, remove_object
from atheriz.singletons.get import (
    get_node_handler,
    get_map_handler,
    get_server_channel,
    get_unique_id,
    get_loggedin_cmdset,
    get_async_ticker,
)
from atheriz.objects.contents import search, group_by_name
from atheriz.commands.base_cmdset import CmdSet
from atheriz.utils import (
    make_iter,
    is_iter,
    get_reverse_link,
    wrap_xterm256,
    ensure_thread_safe,
)
from typing import TYPE_CHECKING, Self
from atheriz.logger import logger
from atheriz.objects import funcparser
import atheriz.settings as settings
from threading import RLock
import time
import dill

if TYPE_CHECKING:
    from atheriz.objects.session import Session
    from atheriz.singletons.node import Node
    from atheriz.objects.base_channel import Channel
    from atheriz.singletons.map import MapInfo
IGNORE_FIELDS = ["lock", "internal_cmdset", "external_cmdset", "access", "_contents", "session"]
_MSG_CONTENTS_PARSER = funcparser.FuncParser(funcparser.ACTOR_STANCE_CALLABLES)


class Object:
    appearance_template = "{name}: {desc}{things}"

    def __init__(self):
        self.lock = RLock()
        self.id = -1
        self.is_deleted = False
        self.is_modified = True
        self.name = ""
        self.desc = ""
        # symbol to be used on map
        self.symbol = "X"
        self.move_verb = "walk"
        self.aliases: list[str] = []
        self.internal_cmdset: CmdSet | None = None
        self.external_cmdset: CmdSet | None = None
        self.date_created = None
        self.location = None
        self.home = None
        self._contents = set()
        self.privilege_level = 0
        self.is_connected = False
        self.created_by = -1
        self.last_touched_by = -1
        self.is_pc = False
        self.is_npc = False
        self.is_item = False
        self.is_mapable = False
        self.is_container = False
        self.is_script = False
        self._is_tickable = False
        self.is_account = False
        self.is_channel = False
        self.is_node = False
        self._tick_seconds = settings.DEFAULT_TICK_SECONDS
        self.last_map_time = time.time()
        self.quelled = False
        self.map_enabled = True
        self._seconds_played = 0
        # list of channel ids subscribed to
        self.channels: list[int] = []
        self.session: Session | None = None
        self.locks: dict[str, list[Callable]] = {}
        if settings.SLOW_LOCKS:
            self.access = self._safe_access
        else:
            self.access = self._fast_access
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    @classmethod
    def create(
        cls,
        caller: Object | None,
        name: str,
        desc: str = "",
        aliases: list[str] | None = None,
        is_pc: bool = False,
        is_item: bool = False,
        is_npc: bool = False,
        is_mapable: bool = False,
        is_container: bool = False,
        is_tickable: bool = False,
        tick_seconds: float = settings.DEFAULT_TICK_SECONDS,
    ) -> Self:
        """
        Create a new object.

        Args:
            session (Session | None): The session to create the object for.
            name (str): The name of the object.
            is_pc (bool, optional): Whether the object is a player character. Defaults to False.
            is_item (bool, optional): Whether the object is an item. Defaults to False.
            is_npc (bool, optional): Whether the object is an NPC. Defaults to False.
            is_mapable (bool, optional): Whether the object is mapable. Defaults to False.
            is_container (bool, optional): Whether the object is a container. Defaults to False.
            is_tickable (bool, optional): Whether the object is tickable. Defaults to False.

        Returns:
            Self: The created object.
        """
        obj = cls()
        obj.id = get_unique_id()
        obj.date_created = time.time()
        if caller:
            obj.created_by = caller.id
        obj.is_pc = is_pc
        obj.is_mapable = is_mapable
        obj.is_container = is_container
        if is_pc:
            obj.is_mapable = True
            obj.is_container = True
        obj.is_item = is_item
        obj.is_npc = is_npc
        obj.is_tickable = is_tickable
        obj.name = name
        obj.desc = desc
        obj._tick_seconds = tick_seconds
        obj.aliases = aliases if aliases else []
        obj.internal_cmdset = CmdSet()
        obj.external_cmdset = CmdSet()
        obj.is_modified = True
        if is_tickable:
            get_async_ticker().add_coro(obj.at_tick, tick_seconds)
        add_object(obj)
        obj.at_create()
        obj.add_lock("delete", lambda x: x.id != obj.id)
        return obj

    def get_save_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for saving this object.
        """
        sql = "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        with self.lock:
            object.__setattr__(self, "is_modified", False)
            params = (self.id, dill.dumps(self))
        return sql, params

    def get_del_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for deleting this object.
        """
        return "DELETE FROM objects WHERE id = ?", (self.id,)

    def delete(self, caller: Object, recursive: bool = True) -> list[tuple[str, tuple]] | None:
        """Delete this object. If recursive, delete contents recursively.
        If not, move contents to container location.

        Args:
            recursive (bool, optional): Delete contents recursively. Defaults to True.

        Returns:
            list[tuple[str, tuple]] | None: A list of SQL operations to execute, or None if deletion was aborted.
        """
        if not self.at_delete(caller):
            return None

        ops = []

        def _delete_object(obj: Object):
            if obj.location:
                obj.location.remove_object(obj)
                obj.location = None

            if obj.is_connected and obj.session and obj.session.connection:
                obj.session.account.remove_character(obj)
                obj.session.connection.close()
            obj.is_deleted = True
            ops.append(obj.get_del_ops())
            remove_object(obj)

        def _delete_recursive(obj: Object):
            if obj.contents:
                for content in list(obj.contents):
                    _delete_recursive(content)
            _delete_object(obj)

        def _move_contents(obj: Object, loc: Object | Node | None):
            if obj.contents:
                for content in list(obj.contents):
                    content.move_to(loc)
            _delete_object(obj)

        if recursive:
            _delete_recursive(self)
        else:
            _move_contents(self, self.location)

        return ops

    def at_delete(self, caller: Object) -> bool:
        """Called before an object is deleted, aborts deletion if False"""
        if not self.access(caller, "delete"):
            caller.msg(f"You cannot delete {self.get_display_name(caller)}.")
            logger.info(
                f"{caller.name} ({caller.id}) tried to delete {self.get_display_name(caller)} ({self.id}) but failed."
            )
            return False
        return True

    def at_create(self):
        """Called after an object is created."""
        pass

    def _safe_access(self, accessing_obj: Object, name: str):
        if accessing_obj.is_superuser and name != "delete":
            return True
        with self.lock:
            lock_list = self.locks.get(name, [])
            for lock in lock_list:
                if not lock(accessing_obj):
                    return False
            return True

    def _fast_access(self, accessing_obj: Object, name: str):
        if accessing_obj.is_superuser and name != "delete":
            return True
        lock_list = self.locks.get(name, [])
        for lock in lock_list:
            if not lock(accessing_obj):
                return False
        return True

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("session", None)
            state.pop("lock", None)
            state.pop("access", None)
            if loc := state.get("location"):
                if loc.is_node:
                    state["location"] = loc.coord
                else:
                    state["location"] = loc.id
            if home := state.get("home"):
                if home.is_node:
                    state["home"] = home.coord
                else:
                    state["home"] = home.id
            return state

    def __setstate__(self, state):
        # this object.__setattr__ bullshit is for bypassing the thread-safety patch
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        if hasattr(self, "_contents") and not isinstance(self._contents, set):
            object.__setattr__(self, "_contents", set(self._contents))
        object.__setattr__(self, "session", None)
        if loc := state.get("location"):
            if isinstance(loc, int):
                object.__setattr__(self, "location", get(loc))
            else:
                object.__setattr__(self, "location", get_node_handler().get_node(loc))
        if home := state.get("home"):
            if isinstance(home, int):
                object.__setattr__(self, "home", get(home))
            else:
                object.__setattr__(self, "home", get_node_handler().get_node(home))
        if settings.SLOW_LOCKS:
            object.__setattr__(self, "access", self._safe_access)
        else:
            object.__setattr__(self, "access", self._fast_access)
        if hasattr(self, "_is_tickable") and self._is_tickable:
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

    @property
    def seconds_played(self):
        return self._seconds_played + (time.time() - self.session.conn_time if self.session else 0)

    @seconds_played.setter
    def seconds_played(self, value):
        self._seconds_played = value

    def at_init(self):
        """
        Called after this object is deserialized and all attributes are set.
        """
        pass

    def at_tick(self):
        """
        Called every tick.
        """
        pass

    def at_alarm(self, time: dict, data):
        """
        Called when an alarm goes off. See time.py for time format.
        """
        pass

    def at_disconnect(self):
        self.is_connected = False
        self.session = None
        channel = get_server_channel()
        if channel:
            channel.msg(f"{self.name} has disconnected.")
        if settings.AUTOSAVE_PLAYERS_ON_DISCONNECT:
            save_objects()

    def subscribe(self, channel: Channel):
        """Subscribe to a channel."""
        with self.lock:
            if channel.id not in self.channels:
                self.channels.append(channel.id)
                cmd = channel.get_command()
                self.internal_cmdset.add(cmd)
                channel.add_listener(self)

    def unsubscribe(self, channel: Channel):
        """Unsubscribe from a channel."""
        with self.lock:
            if channel.id in self.channels:
                self.channels.remove(channel.id)
                cmd = channel.get_command()
                self.internal_cmdset.remove(cmd)
                channel.remove_listener(self)

    def search(self, query: str):
        return search(self, query)

    def at_legend_update(
        self,
        legend: list[tuple[str, str, tuple[int, int]]],
        show_legend: bool = True,
        area: str = "Somewhere",
    ):
        self.msg(legend={"area": area, "legend": legend, "show_legend": show_legend})

    def at_map_update(
        self,
        map: str,
        legend: list[tuple[str, str, tuple[int, int]]],
        min_x: int,
        max_y: int,
        show_legend: bool = True,
        area: str = "Somewhere",
    ):
        # Calculate player position relative to the rendered map string
        # The map string is rendered with (min_x, max_y) at top-left
        pos = (0, 0)
        if self.location:
            player_x = self.location.coord[1]
            player_y = self.location.coord[2]
            # rel_x = column index in map string (0 = left)
            # rel_y = row index in map string (0 = top)
            rel_x = player_x - min_x
            rel_y = max_y - player_y
            pos = (rel_x, rel_y)
        self.msg(
            map={
                "map": map,
                "pos": pos,
                "symbol": self.symbol,
                "legend": legend,
                "min_x": min_x,
                "max_y": max_y,
                "area": area,
                "show_legend": show_legend,
            }
        )
        self.last_map_time = time.time()

    def at_pre_map_render(self, grid: dict[tuple[int, int], str]) -> dict[tuple[int, int], str]:
        """
        to modify map before it's been rendered for this character
        mapables and legend entries with coords will be placed over this map
        """
        return grid

    def add_objects(self, objs: list[Object]):
        """
        add objects to this object's inventory
        Args:
            objs (list): list of objects to add
        """
        with self.lock:
            self._contents.update([obj.id for obj in objs])

    def add_object(self, obj: Object):
        """
        add object to this object's inventory
        Args:
            obj: object to add
        """
        with self.lock:
            self._contents.add(obj.id)
            self.is_modified = True

    def remove_object(self, obj):
        """
        remove object from this object's inventory
        Args:
            obj (Object): object to remove
        """
        with self.lock:
            self._contents.discard(obj.id)
            self.is_modified = True

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

    @property
    def contents(self) -> list[Object]:
        with self.lock:
            return get(self._contents)

    @property
    def is_superuser(self):
        return (self.privilege_level >= 4) and not self.quelled

    @property
    def is_builder(self):
        return self.privilege_level >= 3 and not self.quelled

    def execute_cmd(self, raw_string, session=None, **kwargs):
        pass

    def msg(self, *args, **kwargs):
        from_obj = kwargs.pop("from_obj", None)
        if from_obj:
            for obj in make_iter(from_obj):
                obj.at_msg_send(to_obj=self, **kwargs)
        if "text" in kwargs:
            if not self.at_msg_receive(from_obj=from_obj, **kwargs):
                return
        elif args:
            if not self.at_msg_receive(text=args[0], from_obj=from_obj):
                return
        if self.session is not None:
            self.session.msg(*args, **kwargs)

    # this is from Evennia (https://github.com/evennia/evennia)
    # see EVENNIA_LICENSE.txt for license (BSD-3-Clause)

    def for_contents(self, func, exclude=None, **kwargs):
        """
        Runs a function on every object contained within this one.

        Args:
            func (callable): Function to call. This must have the
                formal call sign func(obj, **kwargs), where obj is the
                object currently being processed and `**kwargs` are
                passed on from the call to `for_contents`.
            exclude (list, optional): A list of object not to call the
                function on.

        Keyword Args:
            Keyword arguments will be passed to the function for all objects.

        """
        contents = self.contents
        if exclude:
            exclude = make_iter(exclude)
            contents = [obj for obj in contents if obj not in exclude]
        for obj in contents:
            func(obj, **kwargs)

    # this is from Evennia (https://github.com/evennia/evennia)
    # see EVENNIA_LICENSE.txt for license (BSD-3-Clause)
    def msg_contents(
        self,
        text=None,
        exclude=None,
        from_obj=None,
        mapping=None,
        raise_funcparse_errors=False,
        **kwargs,
    ):
        """
        Emits a message to all objects inside this object.

        Args:
            text (str or tuple): Message to send. If a tuple, this should be
                on the valid OOB outmessage form `(message, {kwargs})`,
                where kwargs are optional data passed to the `text`
                outputfunc. The message will be parsed for `{key}` formatting and
                `$You/$you()/$You()`, `$obj(name)`, `$conj(verb)` and `$pron(pronoun, option)`
                inline function callables.
                The `name` is taken from the `mapping` kwarg {"name": object, ...}`.
                The `mapping[key].get_display_name(looker=recipient)` will be called
                for that key for every recipient of the string.
            exclude (list, optional): A list of objects not to send to.
            from_obj (Object, optional): An object designated as the
                "sender" of the message. See `DefaultObject.msg()` for
                more info. This will be used for `$You/you` if using funcparser inlines.
            mapping (dict, optional): A mapping of formatting keys
                `{"key":<object>, "key2":<object2>,...}.
                The keys must either match `{key}` or `$You(key)/$you(key)` markers
                in the `text` string. If `<object>` doesn't have a `get_display_name`
                method, it will be returned as a string. Pass "you" to represent the caller,
                this can be skipped if `from_obj` is provided (that will then act as 'you').
            raise_funcparse_errors (bool, optional): If set, a failing `$func()` will
                lead to an outright error. If unset (default), the failing `$func()`
                will instead appear in output unparsed.

            **kwargs: Keyword arguments will be passed on to `obj.msg()` for all
                messaged objects.

        Notes:
            For 'actor-stance' reporting (You say/Name says), use the
            `$You()/$you()/$You(key)` and `$conj(verb)` (verb-conjugation)
            inline callables. This will use the respective `get_display_name()`
            for all onlookers except for `from_obj or self`, which will become
            'You/you'. If you use `$You/you(key)`, the key must be in `mapping`.

            For 'director-stance' reporting (Name says/Name says), use {key}
            syntax directly. For both `{key}` and `You/you(key)`,
            `mapping[key].get_display_name(looker=recipient)` may be called
            depending on who the recipient is.

        Examples:

            Let's assume:

            - `player1.key` -> "Player1",
            - `player1.get_display_name(looker=player2)` -> "The First girl"
            - `player2.key` -> "Player2",
            - `player2.get_display_name(looker=player1)` -> "The Second girl"

            Actor-stance:
            ::

                char.location.msg_contents(
                    "$You() $conj(attack) $you(defender).",
                    from_obj=player1,
                    mapping={"defender": player2})

            - player1 will see `You attack The Second girl.`
            - player2 will see 'The First girl attacks you.'

            Director-stance:
            ::

                char.location.msg_contents(
                    "{attacker} attacks {defender}.",
                    mapping={"attacker":player1, "defender":player2})

            - player1 will see: 'Player1 attacks The Second girl.'
            - player2 will see: 'The First girl attacks Player2'

        """
        # we also accept an outcommand on the form (message, {kwargs})
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

            # director-stance replacements
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

    def at_pre_move(
        self, destination: Node | Object | None, to_exit: str | None = None, **kwargs
    ) -> bool:
        """Called before moving the object."""
        return destination.access(self, "put") if destination else True

    def at_post_move(
        self, destination: Node | Object | None, to_exit: str | None = None, **kwargs
    ) -> None:
        """Called after moving the object."""
        pass

    def move_to(
        self,
        destination: Node | Object | None,
        to_exit: str | None = None,
        force=False,
        announce=True,
        **kwargs,
    ) -> bool:
        """Move this object to a new location."""
        if not force and not self.at_pre_move(destination, to_exit, **kwargs):
            return False
        if destination is None:
            if loc := self.location:
                loc.remove_object(self)
                self.location = None
            self.at_post_move(destination, to_exit, **kwargs)
            return True
        loc = self.location

        def sort_locks(a, b):
            """Helper to sort objects for locking order to avoid deadlocks."""

            def get_key(o):
                # (is_node (0=Node, 1=Object), unique_val)
                # Nodes locked before Objects.
                if getattr(o, "is_node", False):
                    return (0, o.coord)
                return (1, o.id)

            return sorted([a, b], key=get_key)

        def do_item_move():
            # update to be atomic and bypass thread-safety patch
            if loc:
                ordered = sort_locks(loc, destination)
                with ordered[0].lock:
                    with ordered[1].lock:
                        if loc.is_node:
                            if not loc.at_pre_object_leave(destination, to_exit, **kwargs):
                                return False
                            loc.at_object_leave(destination, to_exit, **kwargs)
                        loc._contents.discard(self.id)
                        destination._contents.add(self.id)
                        object.__setattr__(loc, "is_modified", True)
                        object.__setattr__(destination, "is_modified", True)
            else:
                with destination.lock:
                    if destination.is_node:
                        if not destination.at_pre_object_receive(loc, to_exit, **kwargs):
                            return False
                        destination.at_object_receive(loc, to_exit, **kwargs)
                    destination._contents.add(self.id)
                    object.__setattr__(destination, "is_modified", True)
            with self.lock:
                object.__setattr__(self, "location", destination)
                object.__setattr__(self, "last_touched_by", destination.id)
                object.__setattr__(self, "is_modified", True)
            self.at_post_move(destination, to_exit, **kwargs)

        if not destination.is_node:
            do_item_move()
            return True

        # from_exit is NodeLink | None
        reverse_link = (
            get_reverse_link(loc, destination)
            if (loc and loc.is_node and destination.is_node)
            else None
        )
        from_exit = reverse_link.name if reverse_link else None

        def do_move():
            # update to be atomic
            object.__setattr__(self, "is_modified", True)
            old_coord = loc.coord if loc and loc.is_node else None
            if loc:
                ordered = sort_locks(loc, destination)
                with ordered[0].lock:
                    with ordered[1].lock:
                        if announce:
                            self.announce_move_to(loc, to_exit, **kwargs)
                        loc._contents.discard(self.id)
                        destination._contents.add(self.id)
                        object.__setattr__(loc, "is_modified", True)
                        object.__setattr__(destination, "is_modified", True)
                        destination.add_exits(self, internal=True)
                        self.location = destination
                        if announce:
                            self.announce_move_from(destination, from_exit, **kwargs)
            else:
                with destination.lock:
                    destination._contents.add(self.id)
                    object.__setattr__(destination, "is_modified", True)
                    destination.add_exits(self, internal=True)
                    self.location = destination
                    if announce:
                        self.announce_move_from(destination, from_exit, **kwargs)
            if settings.MAP_ENABLED:
                mh = get_map_handler()
                if self.is_pc:
                    # PCs are always listeners (they get map updates)
                    mh.move_listener(self, destination.coord, old_coord)
                if self.is_mapable:
                    # mapables appear on the map
                    mh.move_mapable(self, destination.coord, old_coord)
            self.at_post_move(destination, to_exit, **kwargs)

        do_move()
        if self.is_pc:
            msg = self.at_look(destination)
            if msg:
                self.msg(msg)
        return True

    def get_display_name(self, looker: Object | None = None, **kwargs):
        """Get the display name of this object."""
        return self.name

    def get_display_desc(self, looker: Object | None = None, **kwargs):
        """Get the display description of this object."""
        return self.desc

    def get_display_things(self, looker: Object | None = None, **kwargs):
        """Get the display contents of this object."""
        contents = group_by_name(self.contents, looker)
        if self.is_container and contents:
            return "\n\nInside you see: " + contents
        return ""

    def return_appearance(self, looker: Object | None = None, **kwargs):

        if not looker:
            return ""

        return self.format_appearance(
            self.appearance_template.format(
                name=wrap_xterm256(self.get_display_name(looker, **kwargs), fg=15, bold=True),
                desc=self.get_display_desc(looker, **kwargs),
                things=self.get_display_things(looker, **kwargs),
            ),
            looker,
            **kwargs,
        )

    def at_post_puppet(self, **kwargs):
        self.is_connected = True
        self.session.connection.send_command("logged_in")
        with self.lock:
            for c in self.channels:
                if channel := get(c):
                    channel[0].add_listener(self)
        if channel := get_server_channel():
            channel.msg(f"{wrap_xterm256(self.name, fg=15, bold=True)} (#{self.id}) has logged in.")
        cs = get_loggedin_cmdset()
        commands = [cmd.key for cmd in cs.get_all() if cmd.access(self) and not cmd.hide]
        self.msg(player_commands=commands)
        self.msg(f"You become {wrap_xterm256(self.name, fg=15, bold=True)}.")
        if self.location:
            if settings.MAP_ENABLED:
                mh = get_map_handler()
                mh.add_listener(self)
                if self.is_mapable:
                    mh.add_mapable(self)
            if settings.MAP_ENABLED and self.map_enabled:
                mh = get_map_handler()
                self.msg(map_enable="")
                mi: MapInfo | None = mh.get_mapinfo(self.location.coord[0], self.location.coord[3])
                if mi:
                    mi.render(True)
            self.move_to(self.location)

    def announce_move_from(self, destination: Node, from_exit: str | None, **kwargs):
        if not destination:
            return
        if not from_exit:
            destination.msg_contents(
                f"$You(mover) $conj({self.move_verb}) in.",
                mapping={"mover": self},
                from_obj=self,
                exclude=self,
                type="move",
                internal=True,
                **kwargs,
            )
            return
        if from_exit == "up":
            from_str = "from above"
        elif from_exit == "down":
            from_str = "from below"
        else:
            from_str = f"from the {from_exit}"
        destination.msg_contents(
            f"$You(mover) $conj({self.move_verb}) in {from_str}.",
            mapping={"mover": self},
            from_obj=self,
            exclude=self,
            type="move",
            internal=True,
            **kwargs,
        )

    def announce_move_to(self, source_location: Node, to_exit: str | None, **kwargs):
        if not source_location:
            return
        if not to_exit:
            source_location.msg_contents(
                f"$You(mover) $conj({self.move_verb}) away.",
                mapping={"mover": self},
                from_obj=self,
                exclude=self,
                type="move",
                internal=True,
                **kwargs,
            )
            return
        if to_exit == "up":
            to_str = "upwards"
        elif to_exit == "down":
            to_str = "downwards"
        else:
            to_str = f"to the {to_exit}"
        source_location.msg_contents(
            f"$You(mover) $conj({self.move_verb}) {to_str}.",
            mapping={"mover": self},
            from_obj=self,
            exclude=self,
            type="move",
            internal=True,
            **kwargs,
        )

    def at_msg_receive(self, text: str | None = None, from_obj: Object | None = None, **kwargs):
        """Called by the default `msg` command when this object has received a message."""
        return True

    def at_msg_send(self, text: str | None = None, to_obj: Object | None = None, **kwargs):
        """Called by the default `msg` command when this object sends a message."""
        pass

    def at_desc(self, looker: Object | None = None, **kwargs):
        """Called by the default `look` command when this object is looked at."""
        pass

    def at_pre_get(self, getter: Object, **kwargs):
        """Called by the default `get` command before this object has been picked up."""
        return self.access(getter, "get")

    def at_get(self, getter: Object, **kwargs):
        """Called by the default `get` command when this object has been picked up."""
        pass

    def at_pre_give(self, giver: Object, getter: Object, **kwargs):
        """Called by the default `give` command before this object has been given."""
        return self.access(getter, "give")

    def at_give(self, giver: Object, getter: Object, **kwargs):
        """Called by the default `give` command when this object has been given."""
        pass

    def at_pre_drop(self, dropper: Object, **kwargs):
        """Called by the default `drop` command before this object has been dropped."""
        return self.access(dropper, "drop")

    def at_drop(self, dropper: Object, **kwargs):
        """Called by the default `drop` command when this object has been dropped."""
        pass

    def at_pre_say(self, message: str, **kwargs):
        """Called by the default `say` command before this object says something."""
        return message

    # this is from Evennia, see EVENNIA_LICENSE.txt
    def at_say(
        self,
        message: str,
        msg_self=None,
        msg_location=None,
        receivers=None,
        msg_receivers=None,
        **kwargs,
    ):
        """
        Display the actual say (or whisper) of self.

        This hook should display the actual say/whisper of the object in its
        location.  It should both alert the object (self) and its
        location that some text is spoken.  The overriding of messages or
        `mapping` allows for simple customization of the hook without
        re-writing it completely.

        Args:
            message (str): The message to convey.
            msg_self (bool or str, optional): If boolean True, echo `message` to self. If a string,
                return that message. If False or unset, don't echo to self.
            msg_location (str, optional): The message to echo to self's location.
            receivers (DefaultObject or iterable, optional): An eventual receiver or receivers of the
                message (by default only used by whispers).
            msg_receivers(str): Specific message to pass to the receiver(s). This will parsed
                with the {receiver} placeholder replaced with the given receiver.
        Keyword Args:
            whisper (bool): If this is a whisper rather than a say. Kwargs
                can be used by other verbal commands in a similar way.
            mapping (dict): Pass an additional mapping to the message.

        Notes:


            Messages can contain {} markers. These are substituted against the values
            passed in the `mapping` argument.
            ::

                msg_self = 'You say: "{speech}"'
                msg_location = '{object} says: "{speech}"'
                msg_receivers = '{object} whispers: "{speech}"'

            Supported markers by default:

            - {self}: text to self-reference with (default 'You')
            - {speech}: the text spoken/whispered by self.
            - {object}: the object speaking.
            - {receiver}: replaced with a single receiver only for strings meant for a specific
              receiver (otherwise 'None').
            - {all_receivers}: comma-separated list of all receivers,
              if more than one, otherwise same as receiver
            - {location}: the location where object is.

        """
        msg_type = "say"
        if kwargs.get("whisper", False):
            # whisper mode
            msg_type = "whisper"
            msg_self = (
                '{self} whisper to {all_receivers}, "\x1b[1;37m{speech}\x1b[0m"'
                if msg_self is True
                else msg_self
            )
            msg_receivers = msg_receivers or '{object} whispers: "\x1b[1;37m{speech}\x1b[0m"'
            msg_location = None
        else:
            msg_self = '{self} say, "\x1b[1;37m{speech}\x1b[0m"' if msg_self is True else msg_self
            msg_location = msg_location or '{object} says, "\x1b[1;37m{speech}\x1b[0m"'
            msg_receivers = msg_receivers or message

        custom_mapping = kwargs.get("mapping", {})
        receivers = make_iter(receivers) if receivers else None
        location = self.location

        if msg_self:
            self_mapping = {
                "self": "You",
                "object": self.get_display_name(self),
                "location": location.get_display_name(self) if location else None,
                "receiver": None,
                "all_receivers": (
                    ", ".join(recv.get_display_name(self) for recv in receivers)
                    if receivers
                    else None
                ),
                "speech": message,
            }
            self_mapping.update(custom_mapping)
            self.msg(text=(msg_self.format_map(self_mapping), {"type": msg_type}), from_obj=self)

        if receivers and msg_receivers:
            receiver_mapping = {
                "self": "You",
                "object": None,
                "location": None,
                "receiver": None,
                "all_receivers": None,
                "speech": message,
            }
            for receiver in make_iter(receivers):
                individual_mapping = {
                    "object": self.get_display_name(receiver),
                    "location": location.get_display_name(receiver),
                    "receiver": receiver.get_display_name(receiver),
                    "all_receivers": (
                        ", ".join(recv.get_display_name(recv) for recv in receivers)
                        if receivers
                        else None
                    ),
                }
                receiver_mapping.update(individual_mapping)
                receiver_mapping.update(custom_mapping)
                receiver.msg(
                    text=(msg_receivers.format_map(receiver_mapping), {"type": msg_type}),
                    from_obj=self,
                )

        if self.location and msg_location:
            location_mapping = {
                "self": "You",
                "object": self,
                "location": location,
                "all_receivers": ", ".join(str(recv) for recv in receivers) if receivers else None,
                "receiver": None,
                "speech": message,
            }
            location_mapping.update(custom_mapping)
            exclude = []
            if msg_self:
                exclude.append(self)
            if receivers:
                exclude.extend(receivers)
            self.location.msg_contents(
                text=(msg_location, {"type": msg_type}),
                from_obj=self,
                exclude=exclude,
                mapping=location_mapping,
            )

    def at_look(self, target: Object | Node | None, **kwargs):
        if target is None:
            return "You see nothing here."
        if not target.access(self, "view"):
            return f"You can't look at '{target.get_display_name(self, **kwargs)}'."
        desc = target.return_appearance(self, **kwargs)
        target.at_desc(looker=self, **kwargs)
        return desc

    def at_desc(self, looker: Object | None = None, **kwargs):
        """
        This is called whenever someone looks at this object.

        Args:
            looker (Object, optional): The object requesting the description.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        """
        pass

    def format_appearance(self, appearance, looker, **kwargs):
        return compress_whitespace(appearance).strip()
