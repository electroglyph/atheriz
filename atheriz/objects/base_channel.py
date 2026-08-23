from __future__ import annotations
from collections import deque
from threading import RLock
import atheriz.settings as settings
from atheriz.logger import logger
from atheriz.utils import wrap_truecolor, ensure_thread_safe
from atheriz.globals.objects import get, add_object_unique, filter_by, remove_object, delete_objects
from atheriz.globals.get import get_unique_id
from atheriz.commands.base_cmd import Command
from datetime import datetime
from atheriz.objects.base_db_ops import DbOps
from atheriz.objects.base_flags import Flags
from atheriz.objects.base_lock import AccessLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class BaseChannelCommand(Command):
    key = "__base_channel"
    desc = "Command for accessing channel"
    category: str = "Communication"

    def __init__(self):
        super().__init__()
        self._channel: Channel | None = None

    @property
    def channel(self) -> Channel:
        """Channel: The channel object this command communicates through."""
        if self._channel is not None and getattr(self._channel, "is_deleted", False):
            self._channel = None
            raise ValueError(f"Channel {self.id} not found.")
        if self._channel is None:
            c = get(self.id)
            if c:
                chan = c[0]
                if getattr(chan, "is_deleted", False):
                    raise ValueError(f"Channel {self.id} not found.")
                self._channel = chan
            else:
                raise ValueError(f"Channel {self.id} not found.")
        return self._channel

    @channel.setter
    def channel(self, channel: Channel):
        """Sets the active channel object and synchronizes the command ID to the channel's ID."""
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
        try:
            ch = self.channel
        except ValueError:
            caller.msg("That channel no longer exists.")
            return
        if getattr(ch, "is_deleted", False):
            caller.msg("That channel no longer exists.")
            return
        if args.unsubscribe:
            caller.unsubscribe(ch)
        # elif args.subscribe:
        #     caller.subscribe(ch)
        elif args.replay:
            if not ch.access(caller, "view"):
                caller.msg("You do not have permission to view this channel.")
                return
            h = ch.get_history()
            if h:
                caller.msg(h)
            else:
                caller.msg("No history available.")
        elif args.message:
            if not ch.access(caller, "send"):
                caller.msg("You do not have permission to send to this channel.")
                return
            ch.msg(args.message, caller)
        else:
            caller.msg(self.parser.format_help())

    def __getstate__(self):
        d = super().__getstate__()
        d.pop("_channel", None)
        return d

    def __setstate__(self, state):
        super().__setstate__(state)
        self._channel = None


class Channel(Flags, DbOps, AccessLock):
    group_save: bool = False

    def __init__(self):
        self.lock = RLock()
        super().__init__()
        self.name: str = ""
        self.desc: str = ""
        self.id: int = -1
        self.created_by: int = -1
        self.command: Command | None = None
        self.history: deque[tuple[int, str, str]] = deque(maxlen=settings.CHANNEL_HISTORY_LIMIT)
        self.listeners: dict[int, Object] = {}
        self.is_channel = True
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    @classmethod
    def create(cls, name: str, caller: Object | None = None) -> "Channel":
        if filter_by(lambda x: x.is_channel and x.name == name):
            raise ValueError(f"Channel {name} already exists.")
        c = cls()
        c.name = name
        c.id = get_unique_id()
        c.created_by = caller.id if caller else -1
        add_object_unique(
            c,
            lambda x: x.is_channel and x.name == name,
            f"Channel {name} already exists.",
        )
        c.at_create()
        return c

    def delete(self, caller: Object | None = None, unused: bool = True) -> bool:
        """
        Delete this channel from the database entirely.
        
        Args:
            caller (Object | None, optional): The object executing the deletion. Defaults to None.
            unused (bool, optional): Unused parameter for API compatibility. Defaults to True.
            
        Returns:
            bool: True if the channel was successfully deleted, False if aborted.
        """
        del unused
        if not self.at_delete(caller):
            return False
        if not self.is_temporary:
            ops = [self.get_del_ops()]
            delete_objects(ops)
        with self.lock:
            listeners = list(self.listeners.values())
            self.listeners.clear()
        for listener in listeners:
            try:
                self._detach_subscriber(listener)
            except Exception:
                logger.error(f"Error detaching subscriber {getattr(listener, 'id', '?')} from channel {self.name}", exc_info=True)
        remove_object(self)
        self.is_deleted = True
        return True

    def _detach_subscriber(self, obj: Object) -> None:
        with obj.lock:
            if self.id in getattr(obj, "channels", []):
                try:
                    obj.channels.remove(self.id)
                except ValueError:
                    pass
                object.__setattr__(obj, "is_modified", True)
            try:
                if getattr(obj, "internal_cmdset", None) is not None:
                    obj.internal_cmdset.remove(self.get_command())
            except Exception:
                pass

    def at_delete(self, caller: Object | None = None) -> bool:
        """
        Called before the channel is deleted.
        
        Args:
            caller (Object | None, optional): The object executing the command. Defaults to None.
            
        Returns:
            bool: True to proceed with deletion, False to stop.
        """
        return True

    def at_create(self):
        """
        Called after a new channel is successfully created.
        """
        pass

    def add_listener(self, listener: Object) -> None:
        """
        Connects an object to this channel to receive broadcasts.
        
        Args:
            listener (Object): The object to subscribe to this channel.
        """
        if getattr(self, "is_deleted", False):
            return
        with self.lock:
            self.listeners[listener.id] = listener

    def remove_listener(self, listener: Object) -> None:
        """
        Disconnects an object from this channel.
        
        Args:
            listener (Object): The object to unsubscribe.
        """
        with self.lock:
            self.listeners.pop(listener.id, None)

    def get_command(self) -> Command | None:
        """
        Generates and retrieves the Command class instance used to converse on this channel.
        
        Returns:
            Command | None: The specialized hook command for this channel.
        """
        with self.lock:
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
        # Read sender attributes BEFORE taking the channel lock: the thread-safe
        # getters acquire the sender's own lock, so reading them under the
        # channel lock would invert the ordering against subscribe()/unsubscribe()
        # (object lock -> channel lock) and deadlock.
        timestamp = int(datetime.now().timestamp())
        sender_name = sender.name if sender else ""
        with self.lock:
            if sender:
                self.history.append((timestamp, sender_name, message))
            else:
                self.history.append((timestamp, "", message))
            self.is_modified = True
            listeners = list(self.listeners.values())
        for listener in listeners:
            listener.msg(self.format_message(timestamp, sender_name, message))

    def format_message(self, timestamp: int, sender: str, message: str) -> str:
        """Format a message. Override in subclasses for custom formatting."""
        if sender:
            return f"({wrap_truecolor(self.name, fg=32, bold=True)}) [{datetime.fromtimestamp(timestamp).strftime(r'%d %B, %Y %H:%M:%S')}] {wrap_truecolor(sender, fg=33, fg_sat=0, bold=True)}: {message}"
        return f"({wrap_truecolor(self.name, fg=32, bold=True)}) [{datetime.fromtimestamp(timestamp).strftime(r'%d %B, %Y %H:%M:%S')}] {message}"

    def get_history(self, count: int = settings.CHANNEL_HISTORY_LIMIT) -> str:
        """Return last 'count' messages, oldest first, each formatted with newline."""
        with self.lock:
            entries = list(self.history)[-count:] if count else []
        lines = []
        for timestamp, sender, message in entries:
            formatted = self.format_message(timestamp, sender, message)
            lines.append(formatted + "\n")
        return "".join(lines)

    def clear_history(self) -> None:
        """Clear all history from the channel."""
        with self.lock:
            self.history.clear()
            self.is_modified = True

    def __getstate__(self) -> dict:
        with self.lock:
            state = self.__dict__.copy()
            for cls in type(self).mro():
                # remove excluded keys
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            # Channel-specific exclusions:
            state.pop("lock", None)
            state.pop("listeners", None)
            return state

    def __setstate__(self, state: dict) -> None:
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        self.listeners = {}
        if not isinstance(self.history, deque):
            self.history = deque(self.history, maxlen=settings.CHANNEL_HISTORY_LIMIT)
        # call __setstate__ for all parent classes
        mro = type(self).mro()
        current_idx = next(
            (i for i, c in enumerate(mro)
             if c.__module__ == 'atheriz.objects.base_channel' and c.__qualname__ == 'Channel'),
            len(mro)
        )
        ancestors = mro[current_idx + 1 :]
        for cls in reversed(ancestors):
            if "__setstate__" in cls.__dict__:
                cls.__setstate__(self, state)
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)
