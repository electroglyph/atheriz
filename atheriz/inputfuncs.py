from __future__ import annotations
from typing import TYPE_CHECKING, Callable
from atheriz.globals.get import get_async_threadpool, get_unloggedin_cmdset, get_loggedin_cmdset
from atheriz.logger import logger
import atheriz.settings as settings
from atheriz.connection_screen import render

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.nodes import Node
    from atheriz.objects.base_obj import Object
    
_IGNORE_KEYS = ["save", "quit", "wander", "exit", "logout", "disconnect"]
_NO_ALIAS_COMMANDS = ["n", "s", "e", "w", "u", "d"]

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


def dispatch_loggedin(puppet: Object, text: str, immediate: bool = False):
    """Resolve and dispatch a raw input line as a logged-in puppet.

    Mirrors the logged-in branch of the ``text`` input handler: command lookup
    (internal cmdset, global cmdset, short/auto aliases, location and inventory
    external cmdsets), access control, and dispatch. Shared by the session text
    handler and ``Object.execute_cmd``.

    With ``immediate=False`` (default) the accepted command is queued on the
    async threadpool and None is returned. With ``immediate=True`` the resolved
    ``(func, caller, eargs)`` job is returned instead, for a caller that is
    already on a game worker and will execute it inline (#31: one queue
    crossing per network message).
    """
    if not text:
        return None
    parts = text.split(" ", 1)
    raw_cmd_key = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""
    matched_alias = raw_cmd_key

    cmd = None
    if puppet.internal_cmdset:
        cmd = puppet.internal_cmdset.get(raw_cmd_key)
    if not cmd:
        cmd = get_loggedin_cmdset().get(raw_cmd_key)
    if not cmd:
        # handle aliasing / short commands
        # this makes 'bleh work as `say bleh`
        cmd = get_loggedin_cmdset().get(text[:1])
        if cmd:
            matched_alias = text[:1]
            cmd_args = text[1:]
        else:
            # check for commands provided by objects in the player's location
            loc = puppet.location
            if loc:
                for obj in loc.contents:
                    if obj.external_cmdset and (cmd := obj.external_cmdset.get(raw_cmd_key)):
                        break
            if not cmd:
                # check for commands provided by objects in the player's inventory
                for obj in puppet.contents:
                    if obj.external_cmdset and (cmd := obj.external_cmdset.get(raw_cmd_key)):
                        break

        if not cmd and settings.AUTO_COMMAND_ALIASING:
            if text[:1] in _NO_ALIAS_COMMANDS:
                puppet.msg("You can't do that.")
                return None
            for key in get_loggedin_cmdset().get_keys():
                if key in _IGNORE_KEYS:
                    continue
                if key.startswith(raw_cmd_key):
                    cmd = get_loggedin_cmdset().get(key)
                    matched_alias = key
                    break
        if not cmd:
            cmd = get_loggedin_cmdset().get("none")
            matched_alias = "none"
            cmd_args = raw_cmd_key
    if not cmd:
        return None
    if not cmd.access(puppet):
        puppet.msg("You can't do that.")
        return None
    func, caller, eargs = cmd.execute(puppet, cmd_args, cmdstring=matched_alias)
    if not func:
        logger.warning(f"Command {raw_cmd_key} execute returned no func")
        return None
    if immediate:
        return (func, caller, eargs)
    get_async_threadpool().add_task(func, caller, eargs)
    return None


def _resolve_unloggedin(connection: Connection, text: str):
    """Resolve a raw input line against the unloggedin cmdset.

    Returns the ``(func, caller, eargs)`` job, or None. Mirrors the
    not-logged-in branch of the ``text`` input handler (aliases, auto-aliasing,
    ``none`` fallback)."""
    parts = text.split(" ", 1)
    raw_cmd_key = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""
    matched_alias = raw_cmd_key

    cmdset = get_unloggedin_cmdset()
    cmd = cmdset.get(raw_cmd_key)
    if not cmd:
        if settings.AUTO_COMMAND_ALIASING:
            for key in cmdset.get_keys():
                if key in _IGNORE_KEYS:
                    continue
                if key.startswith(raw_cmd_key):
                    cmd = cmdset.get(key)
                    matched_alias = key
                    break
        if not cmd:
            cmd = cmdset.get("none")
            matched_alias = "none"
            cmd_args = raw_cmd_key
    if not cmd:
        return None
    func, caller, eargs = cmd.execute(connection, cmd_args, cmdstring=matched_alias)
    return (func, caller, eargs) if func else None


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
            session = connection.session
            atp = get_async_threadpool()

            # if we are waiting for input pass it to the future.
            # check-and-clear must be atomic: the prompt owner (async loop)
            # and disconnect cleanup (protocol thread) also touch input_future.
            with session.lock:
                future = session.input_future
                if future and not future.done():
                    session.input_future = None
                else:
                    future = None
            if future:
                atp.loop.call_soon_threadsafe(future.set_result, text)
                return

            if not text:
                return

            # snapshot the puppet once: it may be swapped mid-dispatch by a
            # puppet/unpuppet/login command on another worker
            with session.lock:
                puppet = session.puppet

            if puppet:
                # Player is logged in
                job = dispatch_loggedin(puppet, text, immediate=True)
            else:
                # Player is NOT logged in
                job = _resolve_unloggedin(connection, text)
            if job:
                # already on a game worker via the connection's input drain:
                # execute inline instead of queueing a second task
                atp.run(*job)
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
            w, h = args[0], args[1]
            if not (isinstance(w, int) and isinstance(h, int)):
                return
            if not (0 < w <= settings.TERM_SIZE_MAX_WIDTH and 0 < h <= settings.TERM_SIZE_MAX_HEIGHT):
                return
            connection.session.term_width = w
            connection.session.term_height = h
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
            w, h = args[0], args[1]
            if not (isinstance(w, int) and isinstance(h, int)):
                return
            if not (0 < w <= settings.MAP_SIZE_MAX_WIDTH and 0 < h <= settings.MAP_SIZE_MAX_HEIGHT):
                return
            connection.session.map_width = w
            connection.session.map_height = h

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
        welcome = render(connection.session)
        connection.msg(welcome)
        connection.msg(prompt=">")
