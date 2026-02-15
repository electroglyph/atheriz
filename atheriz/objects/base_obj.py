import _pytest.doctest
from atheriz.utils import compress_whitespace
from typing import Callable
from atheriz.utils import get_import_path
from atheriz.singletons.objects import get, add_object
from atheriz.singletons.get import (
    get_node_handler,
    get_map_handler,
    get_server_channel,
    get_unique_id,
    get_loggedin_cmdset,
    get_async_ticker,
)
from atheriz.objects.persist import save
from atheriz.objects.contents import search, group_by_name
from atheriz.commands.cmdset import CmdSet
from atheriz.utils import (
    make_iter,
    is_iter,
    get_reverse_link,
    wrap_xterm256,
    tuple_to_str,
    str_to_tuple,
    ensure_thread_safe,
)
from typing import TYPE_CHECKING, Self
from atheriz.logger import logger
from atheriz.objects import funcparser
import atheriz.settings as settings
from threading import Lock, RLock
import time
import dill
import base64

if TYPE_CHECKING:
    from atheriz.commands.cmdset import CmdSet
    from atheriz.objects.session import Session
    from atheriz.singletons.node import Node, NodeLink
    from atheriz.objects.base_account import Account
    from atheriz.objects.base_channel import Channel
    from atheriz.singletons.map import MapInfo
IGNORE_FIELDS = ["lock", "internal_cmdset", "external_cmdset", "access", "_contents", "session"]
_MSG_CONTENTS_PARSER = funcparser.FuncParser(funcparser.ACTOR_STANCE_CALLABLES)
_LEGEND_ENTRY = None


class Object:
    appearance_template = "{name}: {desc}{things}"

    def __init__(self):
        self.lock = RLock()
        self.id = -1
        self.is_deleted = False
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
        # self.account: Account | None = None
        self.locks: dict[str, list[Callable]] = {}
        self.group_save = True
        if settings.SLOW_LOCKS:
            self.access = self._safe_access
        else:
            self.access = self._fast_access
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    @classmethod
    def create(
        cls,
        session: Session | None,
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
        if session:
            obj.session = session
            obj.created_by = session.account.id if session.account else -1
            if is_pc and session.account:
                obj.has_account = True
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
        obj.group_save = not is_pc
        obj.internal_cmdset = CmdSet()
        obj.external_cmdset = CmdSet()
        if is_tickable:
            get_async_ticker().add_coro(obj.at_tick, tick_seconds)
        add_object(obj)
        return obj

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

    def __getstate__(self):
        d = self.__dict__.copy()
        for field in IGNORE_FIELDS:
            d.pop(field, None)
        d["_contents"] = list(self._contents)
        if self.internal_cmdset:
            d["internal_cmdset"] = self.internal_cmdset.__getstate__()
        else:
            d["internal_cmdset"] = None
        if self.external_cmdset:
            d["external_cmdset"] = self.external_cmdset.__getstate__()
        else:
            d["external_cmdset"] = None
        d["__import_path__"] = get_import_path(self)
        d["locks"] = base64.b64encode(dill.dumps(self.locks)).decode("utf-8")
        if self.location and self.location.is_node:
            d["location"] = tuple_to_str(self.location.coord)
        elif self.location:
            d["location"] = self.location.id
        else:
            d["location"] = None
        d["home"] = tuple_to_str(self.home) if self.home else None
        return d

    def __setstate__(self, state):
        self.locks = dill.loads(base64.b64decode(state["locks"]))
        del state["locks"]
        self._contents = set(state["_contents"])
        del state["_contents"]
        self.__dict__.update(state)
        if state.get("internal_cmdset"):
            self.internal_cmdset = CmdSet()
            self.internal_cmdset.__setstate__(state["internal_cmdset"])
        else:
            self.internal_cmdset = None

        if state.get("external_cmdset"):
            self.external_cmdset = CmdSet()
            self.external_cmdset.__setstate__(state["external_cmdset"])
        else:
            self.external_cmdset = None
        nh = get_node_handler()
        if state["location"]:
            if isinstance(state["location"], str):
                self.location = nh.get_node(str_to_tuple(state["location"]))
            else:
                loc = get(state["location"])
                if loc:
                    self.location = loc[0]
                else:
                    self.location = None
        else:
            self.location = None
        self.home = str_to_tuple(state["home"]) if state["home"] else None
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
            with self.lock:
                save(self)
            if self._contents:
                save(self.contents)

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

    def remove_object(self, obj):
        """
        remove object from this object's inventory
        Args:
            obj (Object): object to remove
        """
        with self.lock:
            self._contents.discard(obj.id)

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
    def legend_entry(self):
        global _LEGEND_ENTRY
        if not _LEGEND_ENTRY:
            from atheriz.singletons.map import LegendEntry as _LEGEND_ENTRY
        loc: Node | None = self.location
        if loc and loc.is_node:  # full coord is (area(str),x,y,z) ... but maps only want about x,y
            return _LEGEND_ENTRY(self.symbol, self.name, (loc.coord[1], loc.coord[2]))
        else:
            return None

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

    def move_to(
        self,
        destination: Node | Object | None,
        to_exit: str | None = None,
        force=False,
        announce=True,
    ) -> bool:
        """Move this object to a new location."""
        if destination is None:
            return False
        if not destination.access(self, "put"):
            return False
        loc = self.location
        def do_item_move():
            # update to be atomic and bypass thread-safety patch
            if loc:
                with loc.lock:
                    with destination.lock:
                        loc._contents.discard(self.id)
                        object.__setattr__(self, "location", destination)
                        destination._contents.add(self.id)
                        object.__setattr__(self, "last_touched_by", destination.id)
            else:
                with destination.lock:
                    object.__setattr__(self, "location", destination)
                    destination._contents.add(self.id)
                    object.__setattr__(self, "last_touched_by", destination.id)
            with self.lock:
                object.__setattr__(self, "location", destination)
                object.__setattr__(self, "last_touched_by", destination.id)

        if not destination.is_node:
            pre = self.at_pre_move(destination, None)
            if not force:
                if not pre:
                    return False
                else:
                    do_item_move()
            else:
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
            # update to be atomic and bypass thread-safety patch
            old_coord = loc.coord if loc and loc.is_node else None
            if loc:
                with loc.lock:
                    with destination.lock:
                        if announce:
                            self.announce_move_to(loc, to_exit)
                        loc._contents.discard(self.id)
                        destination._contents.add(self.id)
                        destination._add_exits(self)
                        self.location = destination
                        if announce:
                            self.announce_move_from(destination, from_exit)
            else:
                with destination.lock:
                    destination._contents.add(self.id)
                    destination._add_exits(self)
                    self.location = destination
                    if announce:
                        self.announce_move_from(destination, from_exit)
            if settings.MAP_ENABLED:
                mh = get_map_handler()
                if self.is_pc:
                    # PCs are always listeners (they view the map)
                    mh.move_listener(self, destination.coord, old_coord)
                if self.is_mapable:
                    # mapables appear on the map
                    mh.move_mapable(self, destination.coord, old_coord)
            self.at_post_move(destination, to_exit)

        pre = self.at_pre_move(destination, to_exit)
        if not force:
            if not pre:
                return False
            else:
                do_move()
        else:
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

    def at_server_reload(self):
        """
        This hook is called after the server is reloaded.
        """
        # reloading resets channel listeners, so we need to re-add them
        with self.lock:
            for c in self.channels:
                if channel := get(c):
                    channel[0].add_listener(self)

    def at_server_shutdown(self):
        """
        This hook is called whenever the server is shutting down fully
        (i.e. not for a restart).

        """
        pass

    def announce_move_from(self, destination: Node | Object, from_exit: str | None):
        if not destination:
            return
        if not from_exit:
            destination.msg_contents(
                f"$You(mover) $conj({self.move_verb}) in.",
                mapping={"mover": self},
                from_obj=self,
                exclude=self,
                type="move",
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
        )

    def announce_move_to(self, source_location: Node | Object, to_exit: str | None):
        if not source_location:
            return
        if not to_exit:
            source_location.msg_contents(
                f"$You(mover) $conj({self.move_verb}) away.",
                mapping={"mover": self},
                from_obj=self,
                exclude=self,
                type="move",
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
        )

    def at_pre_move(self, destination: Node | Self, to_exit: str | None) -> bool:
        """Called before the object is moved."""
        return True

    def at_post_move(self, destination: Node | Self, to_exit: str | None) -> None:
        """Called after the object is moved."""
        pass

    def at_msg_receive(self, text=None, from_obj: Object | None = None, **kwargs):
        """
        This hook is called whenever someone sends a message to this
        object using the `msg` method.

        Note that from_obj may be None if the sender did not include
        itself as an argument to the obj.msg() call - so you have to
        check for this. .

        Consider this a pre-processing method before msg is passed on
        to the user session. If this method returns False, the msg
        will not be passed on.

        Args:
            text (str, optional): The message received.
            from_obj (any, optional): The object sending the message.
            **kwargs: This includes any keywords sent to the `msg` method.

        Returns:
            receive (bool): If this message should be received.

        Notes:
            If this method returns False, the `msg` operation
            will abort without sending the message.

        """
        return True

    def at_msg_send(self, text=None, to_obj=None, **kwargs):
        """
        This is a hook that is called when *this* object sends a
        message to another object with `obj.msg(text, to_obj=obj)`.

        Args:
            text (str, optional): Text to send.
            to_obj (any, optional): The object to send to.
            **kwargs: Keywords passed from msg().

        Notes:
            Since this method is executed by `from_obj`, if no `from_obj`
            was passed to `DefaultCharacter.msg` this hook will never
            get called.

        """
        pass

    def at_desc(self, looker=None, **kwargs):
        """
        This is called whenever someone looks at this object.

        Args:
            looker (Object, optional): The object requesting the description.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        """
        pass

    def at_pre_get(self, getter, **kwargs):
        """
        Called by the default `get` command before this object has been
        picked up.

        Args:
            getter (DefaultObject): The object about to get this object.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        Returns:
            bool: If the object should be gotten or not.

        Notes:
            If this method returns False/None, the getting is cancelled
            before it is even started.
        """
        return True

    def at_get(self, getter, **kwargs):
        """
        Called by the default `get` command when this object has been
        picked up.

        Args:
            getter (DefaultObject): The object getting this object.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        Notes:
            This hook cannot stop the pickup from happening. Use
            permissions or the at_pre_get() hook for that.

        """
        pass

    def at_pre_give(self, giver, getter, **kwargs):
        """
        Called by the default `give` command before this object has been
        given.

        Args:
            giver (DefaultObject): The object about to give this object.
            getter (DefaultObject): The object about to get this object.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        Returns:
            shouldgive (bool): If the object should be given or not.

        Notes:
            If this method returns `False` or `None`, the giving is cancelled
            before it is even started.

        """
        return True

    def at_give(self, giver, getter, **kwargs):
        """
        Called by the default `give` command when this object has been
        given.

        Args:
            giver (DefaultObject): The object giving this object.
            getter (DefaultObject): The object getting this object.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        Notes:
            This hook cannot stop the give from happening. Use
            permissions or the at_pre_give() hook for that.

        """
        pass

    def at_pre_drop(self, dropper, **kwargs):
        """
        Called by the default `drop` command before this object has been
        dropped.

        Args:
            dropper (DefaultObject): The object which will drop this object.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        Returns:
            bool: If the object should be dropped or not.

        Notes:
            If this method returns `False` or `None`, the dropping is cancelled
            before it is even started.

        """
        if not self.locks.get("drop"):
            # TODO: This if-statment will be removed in Evennia 1.0
            return True
        if not self.access(dropper, "drop", default=False):
            dropper.msg("You cannot drop {obj}").format(obj=self.get_display_name(dropper))
            return False
        return True

    def at_drop(self, dropper, **kwargs):
        """
        Called by the default `drop` command when this object has been
        dropped.

        Args:
            dropper (DefaultObject): The object which just dropped this object.
            **kwargs: Arbitrary, optional arguments for users
                overriding the call (unused by default).

        Notes:
            This hook cannot stop the drop from happening. Use
            permissions or the at_pre_drop() hook for that.

        """
        pass

    def at_pre_say(self, message, **kwargs):
        """
        Before the object says something.

        This hook is by default used by the 'say' and 'whisper'
        commands as used by this command it is called before the text
        is said/whispered and can be used to customize the outgoing
        text from the object. Returning `None` aborts the command.

        Args:
            message (str): The suggested say/whisper text spoken by self.
        Keyword Args:
            whisper (bool): If True, this is a whisper rather than
                a say. This is sent by the whisper command by default.
                Other verbal commands could use this hook in similar
                ways.
            receivers (DefaultObject or iterable): If set, this is the target or targets for the
                say/whisper.

        Returns:
            str: The (possibly modified) text to be spoken.

        """
        return message

    def at_say(
        self,
        message,
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

    def at_desc(self, looker=None, **kwargs):
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
