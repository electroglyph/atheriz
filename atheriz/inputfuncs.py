from __future__ import annotations
from typing import TYPE_CHECKING, Callable
from atheriz.globals.get import get_async_threadpool, get_unloggedin_cmdset, get_loggedin_cmdset, get_map_handler, get_node_handler
from atheriz.logger import logger
import atheriz.settings as settings
import atheriz.globals.mapedit as mapedit
from atheriz.connection_screen import render
from atheriz.utils import wrap_rgb

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.nodes import Node
    from atheriz.objects.base_obj import Object
    
_IGNORE_KEYS = list(settings.AUTO_ALIAS_IGNORED_KEYS)
_NO_ALIAS_COMMANDS = ["n", "s", "e", "w", "u", "d"]

def _is_color(value) -> bool:
    """True for an [r, g, b] color or the [-1, -1, -1] transparent marker."""
    if not isinstance(value, list) or len(value) != 3:
        return False
    if not all(isinstance(v, int) for v in value):
        return False
    if value == [-1, -1, -1]:
        return True
    return all(0 <= v <= 255 for v in value)


def _is_attrs(value) -> bool:
    """True for a list of the three known style flags (no duplicates)."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return False
    return set(value) <= {"bold", "italic", "underline"}

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
    stripped = text.strip(" \t\r\n")
    if not stripped:
        return None
    parts = stripped.split(None, 1)
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
        cmd = get_loggedin_cmdset().get(raw_cmd_key[:1])
        if cmd:
            matched_alias = stripped[:1]
            cmd_args = stripped[1:].lstrip(" \t\r\n")
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
            if raw_cmd_key in _NO_ALIAS_COMMANDS:
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
            cmd_args = stripped
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
    if not get_async_threadpool().add_task(func, caller, eargs):
        logger.warning(f"Command {raw_cmd_key} dropped: task queue full")
    return None


def _resolve_unloggedin(connection: Connection, text: str):
    """Resolve a raw input line against the unloggedin cmdset.

    Returns the ``(func, caller, eargs)`` job, or None. Mirrors the
    not-logged-in branch of the ``text`` input handler (aliases, auto-aliasing,
    ``none`` fallback)."""
    stripped = text.strip(" \t\r\n")
    if not stripped:
        return None
    parts = stripped.split(None, 1)
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
            cmd_args = stripped
    if not cmd:
        return None
    if not cmd.access(connection):
        connection.msg("You can't do that.")
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
            logger.debug("text handler received input")
            session = connection.session
            atp = get_async_threadpool()

            # if we are waiting for input pass it to the future.
            # check-and-clear must be atomic: the prompt owner (async loop)
            # and disconnect cleanup (protocol thread) also touch input_future.
            with session.lock:
                future = session.input_future
                masked = getattr(session, "_input_masked", False)
                if future and not future.done():
                    session.input_future = None
                    session._input_masked = False
                else:
                    future = None
                    masked = False
            if future:
                if masked:
                    try:
                        connection.send_command("echo_on")
                    except Exception:
                        pass
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
            value = args[0]
            if isinstance(value, bool):
                enabled = value
            elif isinstance(value, str):
                enabled = value.lower() == "true"
            else:
                return
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

    @inputfunc()
    def map_edit(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Handle map editor edits authenticated by the rotating key chain.

        Args:
            connection (Connection): The connection sending the edit.
            args (list): Expects `[key (str), seq (int), cells]` where each cell
                is `[x, y, symbol]` (legacy plain char),
                `[x, y, char, fg, bg, attrs]` (fg/bg: [r,g,b] or [-1,-1,-1]
                for transparent; attrs: subset of "bold"/"italic"/"underline"),
                or `["room", fromX, fromY, toX, toY]` (move a room's node).
            kwargs (dict): Unused.
        """
        if len(args) < 3:
            return
        key, seq, cells = args[0], args[1], args[2]
        if not (isinstance(key, str) and isinstance(seq, int) and isinstance(cells, list)):
            return
        for cell in cells:
            if not isinstance(cell, list):
                return
            if cell and cell[0] == "room":
                if not (len(cell) == 5 and all(isinstance(v, int) for v in cell[1:])):
                    return
                continue
            if not (
                len(cell) in (3, 6)
                and isinstance(cell[0], int)
                and isinstance(cell[1], int)
                and isinstance(cell[2], str)
            ):
                return
            if len(cell) == 6:
                if not _is_color(cell[3]) or not _is_color(cell[4]) or not _is_attrs(cell[5]):
                    return
        ip = getattr(connection, "client_host", "?")
        result = mapedit.consume(key, ip, seq)
        if result.status == mapedit.REJECT:
            connection.send_command("map_edit_reject", result.reason)
            return
        if result.status == mapedit.RETRY:
            connection.send_command("map_ack", seq, result.new_key)
            return
        mi = get_map_handler().get_mapinfo(result.chain.area, result.chain.z)
        if mi:
            with mi.batch_update():
                with mi.lock:
                    for cell in cells:
                        if cell and cell[0] == "room":
                            continue
                        x, y, symbol = cell[0], cell[1], cell[2]
                        if symbol == "":
                            mi.pre_grid.pop((x, y), None)
                        elif len(cell) == 3:
                            mi.pre_grid[(x, y)] = symbol
                        else:
                            fg, bg, attrs = cell[3], cell[4], cell[5]
                            mi.pre_grid[(x, y)] = wrap_rgb(
                                symbol,
                                fg=None if fg == [-1, -1, -1] else tuple(fg),
                                bg=None if bg == [-1, -1, -1] else tuple(bg),
                                bold="bold" in attrs,
                                italic="italic" in attrs,
                                underline="underline" in attrs,
                            )
                    mi.map_changed = True
        room_moves = [
            ((cell[1], cell[2]), (cell[3], cell[4])) for cell in cells if cell and cell[0] == "room"
        ]
        if room_moves:
            area_obj = get_node_handler().get_area(result.chain.area)
            grid = area_obj.get_grid(result.chain.z) if area_obj else None
            if grid:
                failed = grid.apply_moves(room_moves)
                for i in failed:
                    logger.warning(
                        f"Map edit room move {room_moves[i]} rejected at save time "
                        f"(area {result.chain.area} z {result.chain.z})"
                    )
        connection.send_command("map_ack", seq, result.new_key)

    @inputfunc()
    def map_validate_moves(self, connection: Connection, args: list, kwargs: dict) -> None:
        """
        Validate prospective room moves for the map editor without applying them.

        Args:
            connection (Connection): The connection sending the request.
            args (list): Expects `[key (str), seq (int), moves]` where each move
                is `[fromX, fromY, toX, toY]`, plus an optional 4th element
                `context`: the editor's pending (unsaved) moves in the same
                shape, simulated first so destinations they vacate count as
                free.
            kwargs (dict): Unused.
        """
        if len(args) < 3 or len(args) > 4:
            return
        key, seq, moves = args[0], args[1], args[2]
        if not (isinstance(key, str) and isinstance(seq, int) and isinstance(moves, list)):
            return
        for move in moves:
            if not (isinstance(move, list) and len(move) == 4 and all(isinstance(v, int) for v in move)):
                return
        context = None
        if len(args) == 4:
            context_arg = args[3]
            if not isinstance(context_arg, list):
                return
            context = []
            for ctx_move in context_arg:
                if not (
                    isinstance(ctx_move, list)
                    and len(ctx_move) == 4
                    and all(isinstance(v, int) for v in ctx_move)
                ):
                    return
                context.append(((ctx_move[0], ctx_move[1]), (ctx_move[2], ctx_move[3])))
        ip = getattr(connection, "client_host", "?")
        result = mapedit.consume(key, ip, seq)
        if result.status == mapedit.REJECT:
            connection.send_command("map_edit_reject", result.reason)
            return
        if result.status == mapedit.RETRY:
            self._send_move_verdict(connection, seq, result.new_key, result.chain.validation or [])
            return
        area_obj = get_node_handler().get_area(result.chain.area)
        grid = area_obj.get_grid(result.chain.z) if area_obj else None
        if grid is None:
            denied = list(range(len(moves)))
        else:
            denied = sorted(
                grid.check_moves(
                    [((m[0], m[1]), (m[2], m[3])) for m in moves],
                    context=context,
                )
            )
        result.chain.validation = denied
        self._send_move_verdict(connection, seq, result.new_key, denied)

    @staticmethod
    def _send_move_verdict(connection: Connection, seq: int, new_key: str, denied: list) -> None:
        if denied:
            connection.send_command("moves_denied", seq, new_key, denied)
        else:
            connection.send_command("moves_ok", seq, new_key)
