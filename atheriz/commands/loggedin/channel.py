from atheriz.singletons.objects import filter_by
from atheriz.singletons.get import get_node_handler
from atheriz.commands.base_cmd import Command
from atheriz.singletons.objects import get_by_type, filter_by_type, get
from atheriz.utils import wrap_xterm256
from atheriz.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel


class ChannelCommand(Command):
    key = "channel"
    desc = "Use and subscribe to channels."
    category: str = "Communication"

    def __init__(self):
        super().__init__()
        self._channel: Channel | None = None
        self.id: int = -1

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
        if args.channel:
            channel = filter_by_type("channel", lambda x: x.name.lower() == args.channel.lower())
            if not channel:
                caller.msg(f"Channel {args.channel} not found.")
                return
            self.channel = channel[0]
        else:
            caller.msg(f"{self.parser.format_help()}")
            return
        if args.unsubscribe:
            caller.unsubscribe(self.channel)
        elif args.subscribe:
            if not self.channel.access(caller, "view"):
                caller.msg("You do not have permission to view this channel.")
                return
            caller.subscribe(self.channel)
        elif args.replay:
            if not self.channel.access(caller, "view"):
                caller.msg("You do not have permission to view this channel.")
                return
            caller.msg(self.channel.get_history())
        elif args.message:
            if not self.channel.access(caller, "send"):
                caller.msg("You do not have permission to send to this channel.")
                return
            self.channel.msg(args.message, caller)
