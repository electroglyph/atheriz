from typing import TYPE_CHECKING, Callable
from atheriz.singletons.get import get_async_threadpool, get_unloggedin_cmdset, get_loggedin_cmdset
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.connection_screen import render

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.nodes import Node
    from atheriz.objects.base_obj import Object
    
_IGNORE_KEYS = ["save", "quit"]

def inputfunc(name: str | None = None):
    """
    Decorator to mark a method as an input handler.
    
    Usage:
        @inputfunc()  # Uses method name as command name
        def my_handler(self, connection, args, kwargs): ...
        
        @inputfunc("custom_name")  # Uses custom command name
        def my_handler(self, connection, args, kwargs): ...
    """
    def decorator(func: Callable) -> Callable:
        func._inputfunc_name = name if name else func.__name__
        return func
    return decorator


class InputFuncs:
    """
    Handles input messages from the client.
    Methods in this class correspond to message commands sent by the client.
    
    To add custom handlers, subclass this and add methods decorated with @inputfunc:
    
        class MyInputFuncs(InputFuncs):
            @inputfunc()
            def my_command(self, connection, args, kwargs):
                # Handle 'my_command' messages
                pass
    """
    
    def get_handlers(self) -> dict[str, Callable]:
        """
        Returns a dict mapping command names to handler methods.
        Automatically discovers all methods decorated with @inputfunc.
        """
        handlers = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr) and hasattr(attr, '_inputfunc_name'):
                handlers[attr._inputfunc_name] = attr
        return handlers

    @inputfunc()
    def text(self, connection: Connection, args: list, kwargs: dict):
        """Handle plain text/command input from the client."""
        try:
            text = str(args[0]) if args else ""
            logger.debug(f"text handler received: {text!r}")

            # if we are waiting for input pass it to the future.
            if connection.session.input_future:
                if not connection.session.input_future.done():
                    get_async_threadpool().loop.call_soon_threadsafe(
                        connection.session.input_future.set_result, text
                    )
                    connection.session.input_future = None
                    return

            if not text:
                return

            parts = text.split(" ", 1)
            cmd_key = parts[0].lower()
            cmd_args = parts[1] if len(parts) > 1 else ""

            atp = get_async_threadpool()

            if connection.session.puppet:
                # Player is logged in
                cmd = connection.session.puppet.internal_cmdset.get(cmd_key)
                if not cmd:
                    cmd = get_loggedin_cmdset().get(cmd_key)
                if cmd:
                    func, caller, eargs = cmd.execute(connection.session.puppet, cmd_args)
                    if func:
                        atp.add_task(func, caller, eargs)
                    else:
                        logger.warning(f"Command {cmd_key} execute returned no func")
                else:
                    # handle aliasing / short commands
                    # this makes 'bleh work as `say bleh`
                    cmd = get_loggedin_cmdset().get(text[:1])
                    if cmd:
                        cmd_key = text[1:]
                    else:
                        # check for commands provided by objects in the players location
                        loc: Object | Node = connection.session.puppet.location
                        if loc:
                            objs = loc.contents
                            for obj in objs:
                                if cmd := obj.external_cmdset.get(cmd_key):
                                    break
                        if not cmd:
                            # check for commands provided by objects in the players inventory
                            objs = connection.session.puppet.contents
                            for obj in objs:
                                if cmd := obj.external_cmdset.get(cmd_key):
                                    break

                    if not cmd and settings.AUTO_COMMAND_ALIASING:
                        keys = get_loggedin_cmdset().get_keys()
                        for key in keys:
                            if key in _IGNORE_KEYS:
                                continue
                            if key.startswith(cmd_key):
                                cmd = get_loggedin_cmdset().get(key)
                                # using the execute below, so set our args properly
                                cmd_key = cmd_args
                                break
                    if not cmd:
                        cmd = get_loggedin_cmdset().get("none")
                    if cmd:
                        func, caller, eargs = cmd.execute(connection.session.puppet, cmd_key)
                        if func:
                            atp.add_task(func, caller, eargs)
            else:
                # Player is NOT logged in
                cmd = get_unloggedin_cmdset().get(cmd_key)
                if cmd:
                    func, caller, eargs = cmd.execute(connection, cmd_args)
                    if func:
                        atp.add_task(func, caller, eargs)
                else:
                    if settings.AUTO_COMMAND_ALIASING:
                        keys = get_unloggedin_cmdset().get_keys()
                        for key in keys:
                            if key in _IGNORE_KEYS:
                                continue
                            if key.startswith(cmd_key):
                                cmd = get_unloggedin_cmdset().get(key)
                                # using the execute below, so set our args properly
                                cmd_key = cmd_args
                                break
                    if not cmd:
                        cmd = get_unloggedin_cmdset().get("none")
                    if cmd:
                        func, caller, eargs = cmd.execute(connection, cmd_key)
                        if func:
                            atp.add_task(func, caller, eargs)
        except Exception:
            import traceback
            logger.error(f"Exception in text handler: {traceback.format_exc()}")

    @inputfunc()
    def term_size(self, connection: Connection, args: list, kwargs: dict):
        """Handle terminal resize events."""
        if len(args) >= 2:
            connection.session.term_width = args[0]
            connection.session.term_height = args[1]
            # connection.send_text(f"Terminal size set to {args[0]}x{args[1]}\r\n")

    @inputfunc()
    def map_size(self, connection: Connection, args: list, kwargs: dict):
        """Handle map resize events."""
        if len(args) >= 2:
            connection.session.map_width = args[0]
            connection.session.map_height = args[1]

    @inputfunc()
    def screenreader(self, connection: Connection, args: list, kwargs: dict):
        """Handle screenreader status update from client."""
        if len(args) > 0:
            enabled = bool(args[0])
            connection.session.screenreader = enabled
            connection.msg(f"Screenreader {'enabled' if enabled else 'disabled'}.")

    @inputfunc()
    def client_ready(self, connection: Connection, args: list, kwargs: dict):
        """Handle client ready signal. Send welcome screen now."""
        try:
            import connection_screen
            import importlib
            # Reload to ensure we get changes if it was modified
            importlib.reload(connection_screen)
            if hasattr(connection_screen, "render"):
                welcome = connection_screen.render(connection.session)
            else:
                 welcome = render(connection.session)    
        except ImportError:
            welcome = render(connection.session)
            
        connection.msg(welcome)
        connection.msg(prompt=">")
