from __future__ import annotations
import threading
from atheriz.globals.objects import filter_by, get
from atheriz.commands.base_cmd import Command
from atheriz.utils import wrap_xterm256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel


class ChannelCommand(Command):
    key = "channel"
    desc = "Use and subscribe to channels."
    category: str = "Communication"
    _channel_cache: dict[str, Channel] = {}
    _channel_cache_lock = threading.RLock()

    def __init__(self):
        super().__init__()
        self._channel: Channel | None = None
        self.id: int = -1

    @property
    def channel(self) -> Channel:
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
        self._channel = channel
        self.id = channel.id

    def setup_parser(self):
        self.parser.add_argument("message", type=str, nargs="*", help="Message to send")
        self.parser.add_argument("-l", "--list", action="store_true", help="List all channels")
        self.parser.add_argument("-c", "--channel", type=str, help="Channel to target")
        self.parser.add_argument(
            "-u", "--unsubscribe", action="store_true", help="Unsubscribe from channel"
        )
        self.parser.add_argument(
            "-s", "--subscribe", action="store_true", help="Subscribe to channel"
        )
        self.parser.add_argument("-r", "--replay", action="store_true", help="View channel history")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        if args.list:
            channels: list[Channel] = filter_by(lambda x: x.is_channel)
            if channels:
                visible = [channel for channel in channels if channel.access(caller, "view")]
                if visible:
                    msg = "\n".join(
                        [
                            f"{wrap_xterm256(channel.name, fg=15, bold=True)}: {channel.desc}"
                            for channel in visible
                        ]
                    )
                    caller.msg(f"{len(visible)} available channels:\n{msg}")
                else:
                    caller.msg("No channels found.")
            else:
                caller.msg("No channels found.")
            return
        if not args.channel:
            caller.msg(f"{self.parser.format_help()}")
            return
        name = args.channel.lower()
        with self._channel_cache_lock:
            channel = self._channel_cache.get(name)
            if channel is not None and (channel.is_deleted or channel.name.lower() != name):
                self._channel_cache.pop(name, None)
                channel = None
        if channel is None:
            result = filter_by(lambda x: x.is_channel and x.name.lower() == name)
            if not result:
                caller.msg(f"Channel {args.channel} not found.")
                return
            channel = result[0]
            if getattr(channel, "is_deleted", False):
                caller.msg(f"Channel {args.channel} not found.")
                return
            with self._channel_cache_lock:
                if getattr(channel, "is_deleted", False) or channel.name.lower() != name:
                    caller.msg(f"Channel {args.channel} not found.")
                    return
                existing = self._channel_cache.get(name)
                if existing is not None and not getattr(existing, "is_deleted", False) and existing.name.lower() == name:
                    channel = existing
                else:
                    self._channel_cache[name] = channel
                    for k, v in list(self._channel_cache.items()):
                        if k != name and v.id == channel.id:
                            self._channel_cache.pop(k, None)
        if args.unsubscribe:
            caller.unsubscribe(channel)
        elif args.subscribe:
            if not channel.access(caller, "view"):
                caller.msg("You do not have permission to view this channel.")
                return
            caller.subscribe(channel)
        elif args.replay:
            if not channel.access(caller, "view"):
                caller.msg("You do not have permission to view this channel.")
                return
            caller.msg(channel.get_history())
        elif args.message:
            # args.message is list due to nargs="*" — join for multi-word
            message = " ".join(args.message) if isinstance(args.message, list) else args.message
            if not message:
                caller.msg(self.print_help())
                return
            if not channel.access(caller, "send"):
                caller.msg("You do not have permission to send to this channel.")
                return
            channel.msg(message, caller)
