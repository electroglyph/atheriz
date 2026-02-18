import dill
from typing import Callable
from collections import deque
from threading import Lock, RLock
import atheriz.settings as settings
from atheriz.utils import wrap_truecolor, ensure_thread_safe
from atheriz.singletons.objects import get, add_object, filter_by, remove_object
from atheriz.singletons.get import get_unique_id
from atheriz.commands.base_cmd import Command
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class BaseChannelCommand(Command):
    key = "__base_channel"
    desc = "Command for accessing channel"
    category: str = "Communication"

    def __init__(self):
        super().__init__()

    @property
    def channel(self) -> Channel:
        if self._channel is None:
            c = get(self.id)
            if c:
                self._channel = c[0]
            else:
                raise ValueError(f"Channel {self.id} not found.")
        return self._channel

    @channel.setter
    def channel(self, channel: Channel):
        self._channel = channel
        self.id = channel.id

    def setup_parser(self):
        self.parser.add_argument("message", type=str, nargs="?", help="Message to send")
        self.parser.add_argument(
            "-u", "--unsubscribe", action="store_true", help="Unsubscribe from channel"
        )
        # self.parser.add_argument("-s","--subscribe", action="store_true", help="Subscribe to channel")
        self.parser.add_argument("-r", "--replay", action="store_true", help="View channel history")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if args.unsubscribe:
            caller.unsubscribe(self.channel)
        # elif args.subscribe:
        #     caller.subscribe(self.channel)
        elif args.replay:
            if not self.channel.access(caller, "view"):
                caller.msg("You do not have permission to view this channel.")
                return
            h = self.channel.get_history()
            if h:
                caller.msg(h)
            else:
                caller.msg("No history available.")
        elif args.message:
            if not self.channel.access(caller, "send"):
                caller.msg("You do not have permission to send to this channel.")
                return
            self.channel.msg(args.message, caller)
        else:
            caller.msg(self.parser.format_help())

    def __getstate__(self):
        d = super().__getstate__()
        del d["_channel"]
        return d

    def __setstate__(self, state):
        super().__setstate__(state)
        self._channel = None


class Channel:
    group_save: bool = False

    def __init__(self):
        self.lock = RLock()
        self.name: str = ""
        self.desc: str = ""
        self.id: int = -1
        self.command: Command | None = None
        self.history: deque[tuple[int, str, str]] = deque(maxlen=settings.CHANNEL_HISTORY_LIMIT)
        self.listeners: dict[int, Object] = {}
        self.locks: dict[str, list[Callable]] = {}
        self.is_pc = False
        self.is_modified = False
        self.is_npc = False
        self.is_item = False
        self.is_mapable = False
        self.is_container = False
        self.is_tickable = False
        self.is_account = False
        self.is_channel = True
        self.is_deleted = False
        self.is_node = False
        if settings.SLOW_LOCKS:
            self.access = self._safe_access
        else:
            self.access = self._fast_access
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

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

    @classmethod
    def create(cls, name: str) -> "Channel":
        results = filter_by(lambda x: x.is_channel and x.name == name)
        if results:
            raise ValueError(f"Channel {name} already exists.")
        c = cls()
        c.name = name
        c.id = get_unique_id()
        add_object(c)
        c.at_create()
        return c

    def get_save_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for saving this object.
        """
        sql = "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        with self.lock:
            params = (self.id, dill.dumps(self))
        return sql, params

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

    def delete(self, caller: Object, unused: bool) -> int:
        del unused
        if not self.at_delete(caller):
            return 0
        self.is_deleted = True
        remove_object(self)
        return 1

    def at_delete(self, caller: Object) -> bool:
        """Called before an object is deleted, aborts deletion if False"""
        return True

    def at_create(self):
        """Called after an object is created."""
        pass

    def add_listener(self, listener: Object) -> None:
        with self.lock:
            self.listeners[listener.id] = listener

    def remove_listener(self, listener: Object) -> None:
        with self.lock:
            self.listeners.pop(listener.id, None)

    def get_command(self) -> Command | None:
        if self.command is not None:
            return self.command
        command = BaseChannelCommand()
        command.key = self.name.lower()
        command.desc = self.desc
        command.channel = self
        command.id = self.id
        self.command = command
        return command

    def msg(self, message: str, sender: Object | None = None) -> None:
        """Send a message to the channel."""
        with self.lock:
            timestamp = int(datetime.now().timestamp())
            if sender:
                self.history.append((timestamp, sender.name, message))
            else:
                self.history.append((timestamp, "", message))
            for listener in self.listeners.values():
                listener.msg(self.format_message(timestamp, sender.name if sender else "", message))

    def format_message(self, timestamp: int, sender: str, message: str) -> str:
        """Format a message. Override in subclasses for custom formatting."""
        if sender:
            return f"({wrap_truecolor(self.name, fg=32, bold=True)}) [{datetime.fromtimestamp(timestamp).strftime(r'%d %B, %Y %H:%M:%S')}] {wrap_truecolor(sender, fg=33, fg_sat=0, bold=True)}: {message}"
        return f"({wrap_truecolor(self.name, fg=32, bold=True)}) [{datetime.fromtimestamp(timestamp).strftime(r'%d %B, %Y %H:%M:%S')}] {message}"

    def get_history(self, count: int = settings.CHANNEL_HISTORY_LIMIT) -> str:
        """Return last 'count' messages, oldest first, each formatted with newline."""
        with self.lock:
            entries = list(self.history)[-count:]
        lines = []
        for timestamp, sender, message in entries:
            formatted = self.format_message(timestamp, sender, message)
            lines.append(formatted + "\n")
        return "".join(lines)

    def clear_history(self) -> None:
        """Clear all history from the channel."""
        with self.lock:
            self.history.clear()

    def __getstate__(self) -> dict:
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            # state.pop("command", None)
            state.pop("access", None)
            state.pop("listeners", None)
            return state

    def __setstate__(self, state: dict) -> None:
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        self.listeners = {}
        # self.command = None
        if not isinstance(self.history, deque):
            self.history = deque(self.history, maxlen=settings.CHANNEL_HISTORY_LIMIT)
        if settings.SLOW_LOCKS:
            object.__setattr__(self, "access", self._safe_access)
        else:
            object.__setattr__(self, "access", self._fast_access)
