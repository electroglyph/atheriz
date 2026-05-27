import asyncio
import threading
from typing import TYPE_CHECKING
import json
from atheriz.utils import strip_ansi

if TYPE_CHECKING:
    from atheriz.objects.session import Session

class BaseConnection:
    """
    Abstract interface for all network connections.
    Specific protocol implementations (WebSocket, Telnet, etc) should inherit
    from this and implement `send_command` and `close`.
    """

    def __init__(self, session_id: str | None = None):
        from atheriz.objects.session import Session
        self.session_id = session_id
        self.session = Session(connection=self)
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
        self.thread_id = threading.get_ident()
        self.lock = threading.RLock()
        self.failed_login_attempts = 0

    # pyrefly: ignore
    def send_command(self, cmd: str, *args, **kwargs):
        """
        Send a command to the client.
        Must be implemented by child classes.
        """
        raise NotImplementedError

    def msg(self, *args, **kwargs):
        """
        Send a text message to this connection.
        Maps simple messages to the robust `send_command` interface.
        """
        cmd = "text"
        if not args and not kwargs:
            return
        args = list(args) or []
        if kwargs:
            text = kwargs.pop("text", None)
            if text:
                args.insert(0, text)
            else:
                k, v = kwargs.popitem()
                cmd = k
                if args:
                    args = [v] + args
                else:
                    args = [v]

        if cmd == "text" and args:
            args[0] = f"{args[0]}\r\n"
            if self.session.screenreader:
                args[0] = strip_ansi(args[0])
        self.send_command(cmd, *args, **kwargs)

    # pyrefly: ignore
    def close(self):
        """
        Close the connection.
        Must be implemented by child classes.
        """
        raise NotImplementedError
