from typing import TYPE_CHECKING, Callable
from atheriz.singletons.get import get_async_threadpool, get_unloggedin_cmdset, get_loggedin_cmdset
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.connection_screen import render

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.nodes import Node
    from atheriz.objects.base_obj import Object
    
_IGNORE_KEYS = ["save", "quit", "wander"]

def inputfunc(name: str | None = None) -> Callable:
    """
    Decorator to mark a method as an input handler for incoming client WebSocket commands.
    
    Args:
        name (str | None, optional): An explicit command name to bind this handler to. 
            If None, the method's name is used. Defaults to None.
            
    Returns:
        Callable: The decorated function, enriched with an `_inputfunc_name` attribute.

    Usage:
        @inputfunc()  # Uses method name as command name
        def text(self, connection, args, kwargs): ...
        
        @inputfunc("custom_name")  # Uses custom command name
        def custom(self, connection, args, kwargs): ...
    """
    def decorator(func: Callable) -> Callable:
        func._inputfunc_name = name if name else func.__name__
        return func
    return decorator


class InputFuncs:
    """
    Handles parsed JSON-RPC input messages from the client.
    Methods in this class correspond to specific message commands sent by the client.
    
    To add custom handlers, subclass this and add methods decorated with @inputfunc:
    
        class MyInputFuncs(InputFuncs):
            @inputfunc()
            def my_command(self, connection, args, kwargs):
                # Handle 'my_command' messages
                pass
    """
    
    def get_handlers(self) -> dict[str, Callable]:
        """
        Scans this class instance to discover and map all methods decorated with @inputfunc.

        Returns:
            dict[str, Callable]: A dictionary mapping the expected input string command 
                to its corresponding handler function.
        """
        handlers = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr) and hasattr(attr, '_inputfunc_name'):
                handlers[attr._inputfunc_name] = attr
        return handlers

    @inputfunc()
    def text(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Handle plain text/command input from the client (e.g. typing commands in the game).
        
        This method is responsible for matching plain text to command sets, checking 
        abbreviations and aliases, and queuing the matched command for execution.

        Args:
            connection (Connection): The connection receiving the text.
            args (list): List of arguments from the RPC call (expects string as first element).
            kwargs (dict): Extra Keyword arguments.
        """
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
    def term_size(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Handle terminal resize events sent natively from the client.

        Args:
            connection (Connection): The connection triggering the resize.
            args (list): Expects a list containing `[width (int), height (int)]`.
            kwargs (dict): Extra Keyword arguments.
        """
        if len(args) >= 2:
            connection.session.term_width = args[0]
            connection.session.term_height = args[1]
            # connection.send_text(f"Terminal size set to {args[0]}x{args[1]}\r\n")

    @inputfunc()
    def map_size(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Handle map UI resize events sent natively from the web client.

        Args:
            connection (Connection): The connection triggering the resize.
            args (list): Expects a list containing `[width (int), height (int)]` of the map pane.
            kwargs (dict): Extra Keyword arguments.
        """
        if len(args) >= 2:
            connection.session.map_width = args[0]
            connection.session.map_height = args[1]

    @inputfunc()
    def screenreader(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Handle screenreader accessibility status updates from the client.

        Args:
            connection (Connection): The connection sending the update.
            args (list): Expects a list containing a single boolean denoting active status.
            kwargs (dict): Extra Keyword arguments.
        """
        if len(args) > 0:
            enabled = bool(args[0])
            connection.session.screenreader = enabled
            connection.msg(f"Screenreader {'enabled' if enabled else 'disabled'}.")

    @inputfunc()
    def client_ready(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Handle the 'client ready' lifecycle signal, prompting the welcome screen to render.

        Args:
            connection (Connection): The connection reporting ready status.
            args (list): Unused.
            kwargs (dict): Unused.
        """
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
