from __future__ import annotations
from atheriz.objects.base_flags import Flags
from atheriz.globals.objects import save_objects
from atheriz.utils import compress_whitespace, get_dir, word_replace
from atheriz.settings import LOUDNESS_LEVELS
from typing import Callable
from atheriz.globals.objects import get, add_object, remove_object
from atheriz.globals.get import (
    get_node_handler,
    get_map_handler,
    get_server_channel,
    get_unique_id,
    get_loggedin_cmdset,
    get_async_ticker,
    get_async_threadpool,
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
from atheriz.objects.base_db_ops import DbOps
from atheriz.objects.base_lock import AccessLock
import time

if TYPE_CHECKING:
    from atheriz.objects.base_script import Script
    from atheriz.objects.session import Session
    from atheriz.globals.node import Node
    from atheriz.objects.base_channel import Channel
    from atheriz.globals.map import MapInfo
_MSG_CONTENTS_PARSER = funcparser.FuncParser(funcparser.ACTOR_STANCE_CALLABLES)


def hookable(func):
    def wrapper(self: "Object", *args, **kwargs):
        h_dict = getattr(self, "hooks", {})
        hooks = h_dict.get(func.__name__, set())

        replace_hooks = [h for h in hooks if getattr(h, "is_replace", False)]
        if replace_hooks:
            return replace_hooks[0](*args, **kwargs)

        before_hooks = [h for h in hooks if getattr(h, "is_before", False)]
        for h in before_hooks:
            h(*args, **kwargs)

        result = func(self, *args, **kwargs)

        after_hooks = [h for h in hooks if getattr(h, "is_after", False)]
        for h in after_hooks:
            result = h(*args, **kwargs)

        if hooks and not (replace_hooks or before_hooks or after_hooks):
            raise ValueError(
                f"Function {func.__name__} has hooks but none are marked with @before, @after, or @replace."
            )

        return result

    return wrapper


class Object(Flags, DbOps, AccessLock):
    appearance_template = "{name}: {desc}{things}"

    def __init__(self):
        # lock should be first!
        self.lock = RLock()
        super().__init__()
        self.id = -1
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
        self._contents: set[int] = set()
        self.privilege_level = settings.Privilege.Guest
        self.created_by = -1
        self.last_touched_by = -1
        self._tick_seconds = settings.DEFAULT_TICK_SECONDS
        self.last_map_time = time.time()
        self.quelled = False
        self.map_enabled = True
        self._seconds_played = 0
        self.scripts: set[int] = set()
        self.hooks: dict[str, set[Callable]] = {}
        # list of channel ids subscribed to
        self.channels: list[int] = []
        self.session: Session | None = None
        self.no_follow: bool = False
        self.following: int | None = None
        self.followers: set[int] = set()
        # this won't be saved:
        self.group_channel: int | None = None
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
            caller (Object | None): The object executing the creation.
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
        obj.can_hear = False
        if is_pc:
            obj.can_hear = True
            obj.is_mapable = True
            obj.is_container = True
            obj.add_lock("view", lambda x: not obj.is_pc or (obj.is_pc and obj.is_connected))
            obj.add_lock("get", lambda x: False)
        obj.is_item = is_item
        obj.is_npc = is_npc
        if is_npc:
            obj.can_hear = True
            obj.add_lock("get", lambda x: False)
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
        # prevent you from accidentally deleting yourself (atari teenage riot!)
        obj.add_lock("delete", lambda caller: caller.id != obj.id)
        return obj

    def add_script(self, script: Script | int):
        """
        Attaches a Script object to this Object, installing any defined hooks.

        Args:
            script (Script | int): The Script object or global ID to attach.
        """
        script = get(script)[0] if isinstance(script, int) else script
        script.install_hooks(self)
        with self.lock:
            self.scripts.add(script.id)

    def remove_script(self, script: Script | int):
        """
        Detaches a Script object from this Object, removing any associated hooks.

        Args:
            script (Script | int): The Script object or global ID to remove.
        """
        script = get(script)[0] if isinstance(script, int) else script
        script.remove_hooks(self)
        with self.lock:
            self.scripts.discard(script.id)

    def has_script_type(self, script_type: str) -> bool:
        """
        Check if this object has a script of the given type.
        It checks the class name of all the attached scripts.

        Args:
            script_type (str): Class name of the script to check for, can be partial. (case-insensitive)

        Returns:
            bool: True if the object has a script of the given type, False otherwise.
        """
        with self.lock:
            if not self.scripts:
                return False
            return any(
                script_type.lower() in scripts[0].__class__.__name__.lower()
                for script_id in self.scripts
                if (scripts := get(script_id))
            )

    def get_scripts_by_type(self, script_type: str) -> list[Script]:
        """
        Get all scripts of a specific type attached to this object.

        Args:
            script_type (str): Class name of the script to check for, can be partial. (case-insensitive)

        Returns:
            list[Script]: A list of Script objects matching the given type.
        """
        matching_scripts = []
        with self.lock:
            if not self.scripts:
                return matching_scripts

            for script_id in self.scripts:
                if scripts := get(script_id):
                    script = scripts[0]
                    if script_type.lower() in script.__class__.__name__.lower():
                        matching_scripts.append(script)

        return matching_scripts

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
            if not obj.is_temporary:
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

    @hookable
    def at_solar_event(self, msg: str):
        """
        Called when a solar event occurs (e.g., sunrise or sunset).
        Receives messages targeted at objects satisfying the `SOLAR_RECEIVER_LAMBDA`.

        Args:
            msg (str): The descriptive message of the event.
        """
        self.msg(msg)

    @hookable
    def at_lunar_event(self, msg: str):
        """
        Called when a lunar event occurs (e.g., full moon phase changes).
        Receives messages targeted at objects satisfying the `LUNAR_RECEIVER_LAMBDA`.

        Args:
            msg (str): The descriptive message of the event.
        """
        self.msg(msg)

    @hookable
    def at_delete(self, caller: Object) -> bool:
        """
        Called before an object is deleted, aborts deletion if False.

        Args:
            caller (Object): The object attempting to trigger the deletion.

        Returns:
            bool: True if deletion should proceed, False to abort.
        """
        if not self.access(caller, "delete"):
            caller.msg(f"You cannot delete {self.get_display_name(caller)}.")
            logger.info(
                f"{caller.name} ({caller.id}) tried to delete {self.get_display_name(caller)} ({self.id}) but failed."
            )
            return False
        return True

    @hookable
    def at_create(self):
        """
        Called after an object is newly created and initialized via `Object.create()`.
        Useful for setting initial variables, inventory generation, or database linkage.
        """
        pass

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            for cls in type(self).mro():
                # remove excluded keys
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            # Object-specific exclusions here:
            state.pop("session", None)
            state.pop("lock", None)
            state.pop("hooks")
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
            # Store as plain int to avoid dill recursion on IntEnum metaclass
            state["privilege_level"] = int(state["privilege_level"])

            return state

    def __setstate__(self, state):
        # this object.__setattr__ bullshit is for bypassing the thread-safety patch
        object.__setattr__(self, "lock", RLock())
        # Restore privilege_level as the proper IntEnum member
        if "privilege_level" in state:
            state["privilege_level"] = settings.Privilege(state["privilege_level"])
        self.__dict__.update(state)
        if hasattr(self, "_contents") and not isinstance(self._contents, set):
            object.__setattr__(self, "_contents", set(self._contents))
        object.__setattr__(self, "session", None)
        object.__setattr__(self, "group_channel", None)
        object.__setattr__(self, "hooks", {})
        # call __setstate__ for all parent classes
        mro = type(self).mro()
        current_idx = next(
            (i for i, c in enumerate(mro) if c.__module__ == "atheriz.objects.base_obj" and c.__qualname__ == "Object"),
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
        This reconstitutes pointers like `location` and `home` from their integer IDs,
        and reschedules any async ticker events or script hooks.
        """
        loc = getattr(self, "location", None)
        if loc:
            if isinstance(loc, int):
                self.location = get(loc)[0] if get(loc) else None
            elif isinstance(loc, tuple):
                self.location = get_node_handler().get_node(loc)

        home = getattr(self, "home", None)
        if home:
            if isinstance(home, int):
                self.home = get(home)[0] if get(home) else None
            elif isinstance(home, tuple):
                self.home = get_node_handler().get_node(home)

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
        """bool: Indicates if this object is currently registered with the asynchronous ticker."""
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
    def seconds_played(self) -> float:
        """float: The total accumulated playtime in seconds for this character/object."""
        return self._seconds_played + (time.time() - self.session.conn_time if self.session else 0)

    @seconds_played.setter
    def seconds_played(self, value):
        self._seconds_played = value

    @hookable
    def at_init(self):
        """
        Called after this object is deserialized and all attributes are set.
        """
        pass

    @hookable
    def at_tick(self):
        """
        Called every tick.
        """
        pass

    @hookable
    def at_alarm(self, time: dict, data):
        """
        Called when an alarm goes off. See time.py for time format.
        """
        pass

    @hookable
    def at_disconnect(self):
        """
        Called when the client connected to this object drops the WebSocket connection.
        Handles internal state updates and optionally triggers an auto-save.
        """
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

    def search(self, query: str) -> list[Object]:
        """
        Search for an object by name or alias inside the contents of this object,
        and within the room this object is standing in.

        Args:
            query (str): The search string to evaluate.

        Returns:
            list[Object]: A list of objects matching the query.
        """
        return search(self, query)

    @hookable
    def at_legend_update(
        self,
        legend: list[tuple[str, str, tuple[int, int]]],
        show_legend: bool = True,
        area: str = "Somewhere",
    ):
        """
        Sends map legend updates directly to the connected client.

        Args:
            legend (list[tuple[str, str, tuple[int, int]]]): Parsed legend data format.
            show_legend (bool, optional): Whether the legend pane should be rendered. Defaults to True.
            area (str, optional): The geographic name of the map area. Defaults to "Somewhere".
        """
        self.msg(legend={"area": area, "legend": legend, "show_legend": show_legend})

    @hookable
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
            coord = self.location.coord
            # Handle both Coord NamedTuple and legacy 4-tuple
            player_x = getattr(coord, "x", coord[1] if len(coord) > 1 else 0)
            player_y = getattr(coord, "y", coord[2] if len(coord) > 2 else 0)
            
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

    @hookable
    def at_pre_map_render(self, grid: dict[tuple[int, int], str]) -> dict[tuple[int, int], str]:
        """
        to modify map before it's been rendered for this character
        mapables and legend entries with coords will be placed over this map
        """
        return grid

    def add_objects(self, objs: list[Object]):
        """
        Add multiple objects to this object's internal inventory.

        Args:
            objs (list[Object]): A list of objects to add.
        """
        with self.lock:
            self._contents.update([obj.id for obj in objs])

    def add_object(self, obj: Object):
        """
        Add a single object to this object's internal inventory.

        Args:
            obj (Object): The object to add.
        """
        with self.lock:
            self._contents.add(obj.id)
            self.is_modified = True

    def remove_object(self, obj: Object):
        """
        Remove a single object from this object's internal inventory.

        Args:
            obj (Object): The object to remove.
        """
        with self.lock:
            self._contents.discard(obj.id)
            self.is_modified = True

    @property
    def contents(self) -> list[Object]:
        """list[Object]: The list of objects currently stored within this object."""
        with self.lock:
            return get(self._contents)

    @property
    def is_superuser(self) -> bool:
        """bool: Indicates if this object possesses superuser administrative rights."""
        return (self.privilege_level >= settings.Privilege.Admin) and not self.quelled

    @property
    def is_builder(self) -> bool:
        """bool: Indicates if this object possesses builder world-editing rights."""
        return self.privilege_level >= settings.Privilege.Builder and not self.quelled

    def execute_cmd(self, raw_string, session=None, **kwargs):
        """
        Mock compatibility method simulating executing a command directly as this object.
        Currently unimplemented.

        Args:
            raw_string (str): The raw string to execute.
            session (Session, optional): The session executing the command.
        """
        pass

    def msg(self, *args, **kwargs):
        """
        Send a direct textual message to this object. If the object is currently
        controlled by a connected session, the message is routed to the client.

        Args:
            *args: Ordered textual messages.
            **kwargs: Extra arguments, primarily including 'from_obj' and 'text'.
        """
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
                    key: (obj.get_display_name(looker=receiver) if hasattr(obj, "get_display_name") else str(obj))
                    for key, obj in mapping.items()
                }
            )

            receiver.msg(text=(outmessage, outkwargs), from_obj=from_obj, **kwargs)

    @hookable
    def at_pre_move(self, destination: Node | Object | None, to_exit: str | None = None, **kwargs) -> bool:
        """
        Called before moving the object. Evaluates the destination's access locks.

        Args:
            destination (Node | Object | None): The target location for the move.
            to_exit (str | None, optional): The name of the exit traversed, if any.
            **kwargs: Extra arguments.

        Returns:
            bool: True if the move should proceed, False to abort.
        """
        if self.location and not self.location.access(self, "exit"):
            return False
        if destination and not destination.access(self, "enter"):
            return False
        return True

    @hookable
    def at_post_move(self, destination: Node | Object | None, to_exit: str | None = None, **kwargs) -> None:
        """
        Called after moving the object successfully completes.

        Args:
            destination (Node | Object | None): The new location of the object.
            to_exit (str | None, optional): The name of the exit traversed, if any.
            **kwargs: Extra arguments.
        """
        pass

    def move_to(
        self,
        destination: Node | Object | None,
        to_exit: str | None = None,
        force=False,
        announce=True,
        **kwargs,
    ) -> bool:
        """
        Execute the complex sequence of moving this object to a new location,
        handling locks, announcements, map updates, and hooks bidirectionally.

        Args:
            destination (Node | Object | None): The target destination.
            to_exit (str | None, optional): The exit traversed. Defaults to None.
            force (bool, optional): If True, bypasses pre-move checks. Defaults to False.
            announce (bool, optional): If True, broadcasts movement strings to rooms. Defaults to True.
            **kwargs: Optional variables passed to hooks.

        Returns:
            bool: True if the move successful, False if aborted.
        """
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
        reverse_link = get_reverse_link(loc, destination) if (loc and loc.is_node and destination.is_node) else None
        from_exit = reverse_link.name if reverse_link else None

        def do_move():
            # update to be atomic
            object.__setattr__(self, "is_modified", True)
            old_coord = loc.coord if loc and loc.is_node else None
            if loc:
                ordered = sort_locks(loc, destination)
                with ordered[0].lock:
                    with ordered[1].lock:
                        loc._contents.discard(self.id)
                        destination._contents.add(self.id)
                        object.__setattr__(loc, "is_modified", True)
                        object.__setattr__(destination, "is_modified", True)
                        destination.add_exits(self, internal=True)
                        self.location = destination
                if announce:
                    self.announce_move_to(loc, to_exit, **kwargs)
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

    def get_display_name(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the display name of this object, customized for the looker.

        Args:
            looker (Object | None, optional): The object looking at this object. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The evaluated name string.
        """
        if self.is_pc and not self.is_connected:
            return f"{self.name} (offline)"
        if not looker:
            return self.name
        if self.access(looker, "view"):
            return self.name
        else:
            if self.is_pc or self.is_npc:
                return "Someone"
            return "Something"

    def get_display_desc(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the display description of this object, customized for the looker.

        Args:
            looker (Object | None, optional): The object looking at this object. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The evaluated description string.
        """
        return self.desc

    def get_display_things(self, looker: Object | None = None, **kwargs) -> str:
        """
        Get the formatted inventory/contents of this object.

        Args:
            looker (Object | None, optional): The object looking at this object. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The formatted string listing contents, or empty string.
        """
        contents = group_by_name(self.contents, looker)
        if self.is_container and contents:
            return "\n\nInside you see: " + contents
        return ""

    def return_appearance(self, looker: Object | None = None, **kwargs) -> str:
        """
        Assembles and formats the complete appearance of this object into a single string.

        Args:
            looker (Object | None, optional): The object observing this object. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            str: The fully formatted appearance string for rendering on the client.
        """
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

    @hookable
    def at_post_puppet(self, **kwargs):
        """
        Called when a Session successfully assumes direct control of this object.
        Re-subscribes to channels, registers with the map system, and loads CmdSets.

        Args:
            **kwargs: Extra arguments.
        """
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
            self.move_to(self.location)
            if settings.MAP_ENABLED and self.map_enabled:
                self.msg(map_enable="")
                mh = get_map_handler()
                mi: MapInfo | None = mh.get_mapinfo(self.location.coord.area, self.location.coord.z)
                if mi:
                    mi.render(True)

    def announce_move_from(self, destination: Node, from_exit: str | None, **kwargs):
        """
        Announces that this object has arrived in a target room.

        Args:
            destination (Node): The node the object has arrived into.
            from_exit (str | None): The name of the exit traversed to get here, if any.
            **kwargs: Extra arguments passed to msg_contents.
        """
        if not destination:
            return
        if not from_exit:
            destination.msg_contents(
                f"$You(mover) $conj({self.move_verb}) in.",
                mapping={"mover": self},
                from_obj=self,
                exclude=self,
                type="move",
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
            **kwargs,
        )

    def announce_move_to(self, source_location: Node, to_exit: str | None, **kwargs):
        """
        Announces that this object has departed a source room.

        Args:
            source_location (Node): The node the object has departed from.
            to_exit (str | None): The name of the exit traversed to leave.
            **kwargs: Extra arguments passed to msg_contents.
        """
        if not source_location:
            return
        if not to_exit:
            source_location.msg_contents(
                f"$You(mover) $conj({self.move_verb}) away.",
                mapping={"mover": self},
                from_obj=self,
                exclude=self,
                type="move",
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
            **kwargs,
        )

    @hookable
    def at_msg_receive(self, text: str | None = None, from_obj: Object | None = None, **kwargs) -> bool:
        """
        Called when this object is about to receive an arbitrary string message.
        Returning False aborts the message delivery.

        Args:
            text (str | None, optional): The message content. Defaults to None.
            from_obj (Object | None, optional): The sender of the message. Defaults to None.
            **kwargs: Extra arguments.

        Returns:
            bool: True if the message should be received, False to reject it.
        """
        return True

    @hookable
    def at_msg_send(self, text: str | None = None, to_obj: Object | None = None, **kwargs) -> None:
        """
        Called when this object sends an arbitrary string message to another object.

        Args:
            text (str | None, optional): The message content. Defaults to None.
            to_obj (Object | None, optional): The intended receiver. Defaults to None.
            **kwargs: Extra arguments.
        """
        pass

    @hookable
    def at_desc(self, looker: Object | None = None, **kwargs) -> None:
        """
        Called when another object looks at this object.

        Args:
            looker (Object | None, optional): The object observing this one. Defaults to None.
            **kwargs: Extra arguments.
        """
        pass

    @hookable
    def at_pre_get(self, getter: Object, **kwargs) -> bool:
        """
        Called before another object attempts to pick up this object.
        Evaluates the "get" lock by default.

        Args:
            getter (Object): The object attempting to get this object.
            **kwargs: Extra arguments.

        Returns:
            bool: True if the get is permitted, False otherwise.
        """
        return self.access(getter, "get")

    @hookable
    def at_get(self, getter: Object, **kwargs) -> None:
        """
        Called after another object successfully picks up this object.

        Args:
            getter (Object): The object that picked up this object.
            **kwargs: Extra arguments.
        """
        pass

    @hookable
    def at_pre_give(self, giver: Object, getter: Object, **kwargs) -> bool:
        """
        Called before this object is given from one inventory to another.
        Evaluates the "give" lock on the receiving object by default.

        Args:
            giver (Object): The object currently holding this object.
            getter (Object): The intended recipient.
            **kwargs: Extra arguments.

        Returns:
            bool: True if the transfer is permitted, False otherwise.
        """
        return self.access(getter, "give")

    @hookable
    def at_give(self, giver: Object, getter: Object, **kwargs) -> None:
        """
        Called after this object is successfully transferred between inventories.

        Args:
            giver (Object): The previous holder of this object.
            getter (Object): The new holder.
            **kwargs: Extra arguments.
        """
        pass

    @hookable
    def at_pre_drop(self, dropper: Object, **kwargs) -> bool:
        """
        Called before this object is dropped from an inventory into the room.
        Evaluates the "drop" lock by default.

        Args:
            dropper (Object): The object attempting to drop this object.
            **kwargs: Extra arguments.

        Returns:
            bool: True if dropping is permitted, False otherwise.
        """
        return self.access(dropper, "drop")

    @hookable
    def at_drop(self, dropper: Object, **kwargs) -> None:
        """
        Called after this object is successfully dropped out of an inventory.

        Args:
            dropper (Object): The actor that dropped this object.
            **kwargs: Extra arguments.
        """
        pass

    @hookable
    def at_pre_say(self, message: str, **kwargs) -> str:
        """
        Called before this object broadcasts a speech message into the room.
        Can intercept and mutate the spoken message.

        Args:
            message (str): The raw string intended to be spoken.
            **kwargs: Extra arguments.

        Returns:
            str: The potentially modified message string.
        """
        return message

    @hookable
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

    @hookable
    def at_hear(self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool):
        """
        Called when this object hears a sound.

        Args:
            emitter (Object): The object that made the sound.
            sound_desc (str): The description of the sound.
            sound_msg (str): The message of the sound.
            loudness (float): The loudness of the sound.
            is_say (bool): Whether the sound is a say.
        """
        if not self.is_pc:
            return
        loc = self.location
        if not loc:
            return
        adj = next((desc for threshold, desc in LOUDNESS_LEVELS if loudness < threshold), "deafening")

        if is_say and sound_msg:
            replace_pct = next((pct for threshold, pct in settings.REPLACE_LEVELS if loudness < threshold), 0)
            if replace_pct > 0:
                sound_msg = word_replace(sound_msg, replace_pct / 100.0)

        emitter_loc = emitter.location
        if emitter_loc == loc or not emitter_loc:
            self.msg(f"{wrap_xterm256(f'You hear something{adj}:', fg=15, bold=True)} {sound_desc}{sound_msg}")
        else:
            z_str = ""
            if emitter_loc.coord.area == loc.coord.area:
                direction = get_dir(loc.coord, emitter_loc.coord)
                z_diff = emitter_loc.coord.z - loc.coord.z
                z_str = "" if z_diff == 0 else ("from above you " if z_diff > 0 else "from below you ")
                self.msg(
                    f"{wrap_xterm256(f'You hear something{adj} {z_str}to the {direction}:', fg=15, bold=True)} {sound_desc}{sound_msg}"
                )

    @hookable
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

    @hookable
    def at_emit_sound(self, sound_desc: str, sound_msg: str, loudness: float, is_say: bool):
        """
        Called when this object emits a sound.

        Args:
            sound_desc (str): The description of the sound.
            sound_msg (str): The message of the sound.
            loudness (float): The loudness of the sound.
            is_say (bool): Whether the sound is a say.
        """
        if not sound_msg:
            return
        loc = self.location
        allow, emitter, sound_desc, sound_msg, loudness, is_say = self.at_pre_emit_sound(
            self, sound_desc, sound_msg, loudness, is_say
        )
        if not allow:
            return
        if loc:
            allow, emitter, sound_desc, sound_msg, loudness, is_say = loc.at_pre_emit_sound(
                self, sound_desc, sound_msg, loudness, is_say
            )
            if not allow:
                return
            for o in loc.contents:
                if o.can_hear:
                    allow, emitter, sound_desc, sound_msg, loudness, is_say = o.at_pre_hear(
                        emitter, sound_desc, sound_msg, loudness, is_say
                    )
                    if not allow:
                        continue
                    o.at_hear(emitter, sound_desc, sound_msg, loudness, is_say)
            c = loc.coord
            nh = get_node_handler()
            area = nh.get_area(c.area)
            if area:
                open = False
                doors = nh.get_doors(c)
                if doors:
                    # update for windows later?
                    for door in doors.values():
                        if door.open:
                            open = True
                            break
                else:
                    # if no doors, we'll just assume room has at least 1 open exit
                    open = True
                attenuation = loc.open_attenuation if open else loc.enclosed_attenuation
                loudness = loudness - attenuation
                from collections import deque
                mcoord = (c.x, c.y, c.z)
                source_local = mcoord
                visited = {source_local}
                seen = {source_local}
                queue = deque()
                for neighbor in area.get_neighbors(source_local):
                    if neighbor:
                        ncoord = (neighbor.coord.x, neighbor.coord.y, neighbor.coord.z)
                        seen.add(ncoord)
                        queue.append((neighbor, loudness))
                while queue:
                    node, node_loudness = queue.popleft()
                    if node:
                        ncoord = (node.coord.x, node.coord.y, node.coord.z)
                        if ncoord in visited:
                            continue
                        visited.add(ncoord)
                        ret = node.at_hear(emitter, sound_desc, sound_msg, node_loudness, is_say)
                        if ret > 0:
                            for neighbor in area.get_neighbors(ncoord):
                                if neighbor:
                                    nnc = (neighbor.coord.x, neighbor.coord.y, neighbor.coord.z)
                                    if nnc not in seen:
                                        seen.add(nnc)
                                        queue.append((neighbor, ret))

    def emit_sound(self, sound_desc: str, sound_msg: str, loudness: float, is_say: bool = False):
        """Emit a sound.

        Args:
            sound_desc (str): Description of the sound
            sound_msg (str): Message of the sound
            loudness (float): Loudness of the sound
            is_say (bool, optional): Whether the sound is a say. Defaults to False.
        """
        atp = get_async_threadpool()
        atp.add_task(self.at_emit_sound, sound_desc, sound_msg, loudness, is_say)

    # this is from Evennia, see EVENNIA_LICENSE.txt
    @hookable
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
                '{self} whisper to {all_receivers}, "\x1b[1;37m{speech}\x1b[0m"' if msg_self is True else msg_self
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
                "all_receivers": (", ".join(recv.get_display_name(self) for recv in receivers) if receivers else None),
                "speech": message,
            }
            self_mapping.update(custom_mapping)
            self.msg(
                text=(msg_self.format_map(self_mapping), {"type": msg_type}),
                from_obj=self,
            )

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
                        ", ".join(recv.get_display_name(recv) for recv in receivers) if receivers else None
                    ),
                }
                receiver_mapping.update(individual_mapping)
                receiver_mapping.update(custom_mapping)
                receiver.msg(
                    text=(
                        msg_receivers.format_map(receiver_mapping),
                        {"type": msg_type},
                    ),
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

    @hookable
    def at_look(self, target: Object | Node | None, **kwargs) -> str:
        """
        Called when this object looks at another target. Evaluates the "view" lock.

        Args:
            target (Object | Node | None): The entity being looked at.
            **kwargs: Extra arguments.

        Returns:
            str: The evaluated appearance string of the target.
        """
        if target is None:
            return "You see nothing here."
        if not target.access(self, "view"):
            return f"You can't look at '{target.get_display_name(looker=self, **kwargs)}'."
        desc = target.return_appearance(looker=self, **kwargs)
        target.at_desc(looker=self, **kwargs)
        return desc

    def format_appearance(self, appearance: str, looker: Object, **kwargs) -> str:
        """
        Compresses and cleans up whitespace on the final appearance string.

        Args:
            appearance (str): The raw multi-line appearance string.
            looker (Object): The object viewing the appearance.
            **kwargs: Extra arguments.

        Returns:
            str: The polished string.
        """
        return compress_whitespace(appearance).strip()
