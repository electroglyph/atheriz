from __future__ import annotations
from typing import TYPE_CHECKING
from atheriz.settings import THREADPOOL_LIMIT
from atheriz.logger import logger
from threading import Lock, RLock

if TYPE_CHECKING:
    from atheriz.commands.loggedin.cmdset import LoggedinCmdSet
    from atheriz.globals.asyncthreadpool import AsyncThreadPool, AsyncTicker
    from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet
    from atheriz.globals.node import NodeHandler
    from atheriz.globals.map import MapHandler
    from atheriz.network.manager import ConnectionManager
    from atheriz.globals.time import GameTime

    # from inflect import engine
    from atheriz.objects.base_channel import Channel

_ASYNC_THREAD_POOL: AsyncThreadPool | None = None
_UNLOGGEDIN_CMDSET: UnloggedinCmdSet | None = None
_LOGGEDIN_CMDSET: LoggedinCmdSet | None = None
_NODE_HANDLER: NodeHandler | None = None
_MAP_HANDLER: MapHandler | None = None
_SERVER_CHANNEL: Channel | None = None
_ASYNC_TICKER: AsyncTicker | None = None
_CONNECTION_MANAGER: ConnectionManager | None = None
_GAME_TIME: GameTime | None = None
# _INFLECT_ENGINE: engine | None = None


# def GetInflectEngine() -> engine:
#     global _INFLECT_ENGINE
#     if not _INFLECT_ENGINE:
#         from inflect import engine
#         _INFLECT_ENGINE = engine()
#     return _INFLECT_ENGINE

_ID_LOCK = Lock()
_ID = -1

# Guards lazy construction of the singleton getters below (double-checked
# locking). RLock so a getter whose constructor calls another getter re-enters
# safely; still serializes construction across threads under free-threading.
_SINGLETON_LOCK = RLock()


def set_id(id: int) -> None:
    """Set the global ID to the given value."""
    with _ID_LOCK:
        global _ID
        _ID = id


def get_unique_id() -> int:
    """Get a unique ID."""
    with _ID_LOCK:
        global _ID
        _ID += 1
        return _ID


def get_game_time() -> GameTime:
    global _GAME_TIME
    with _SINGLETON_LOCK:
        if _GAME_TIME is None:
            from atheriz.globals.time import GameTime

            _GAME_TIME = GameTime()
    return _GAME_TIME


def get_connection_manager() -> ConnectionManager:
    global _CONNECTION_MANAGER
    with _SINGLETON_LOCK:
        if _CONNECTION_MANAGER is None:
            from atheriz.network import connection_manager

            _CONNECTION_MANAGER = connection_manager
    return _CONNECTION_MANAGER


def get_async_ticker() -> AsyncTicker:
    global _ASYNC_TICKER
    with _SINGLETON_LOCK:
        if _ASYNC_TICKER is None:
            from atheriz.globals.asyncthreadpool import AsyncTicker

            _ASYNC_TICKER = AsyncTicker()
    return _ASYNC_TICKER


def get_server_channel() -> Channel | None:
    global _SERVER_CHANNEL
    with _SINGLETON_LOCK:
        if _SERVER_CHANNEL is None:
            from atheriz.globals.objects import filter_by

            c = filter_by(lambda x: x.is_channel and x.name.lower() == "server")
            if c:
                _SERVER_CHANNEL = c[0]
            else:
                logger.error("Server channel not found.")
    return _SERVER_CHANNEL


def get_map_handler() -> MapHandler:
    global _MAP_HANDLER
    with _SINGLETON_LOCK:
        if _MAP_HANDLER is None:
            from atheriz.globals.map import MapHandler

            _MAP_HANDLER = MapHandler()
    return _MAP_HANDLER


def get_loggedin_cmdset() -> LoggedinCmdSet:
    global _LOGGEDIN_CMDSET
    with _SINGLETON_LOCK:
        if _LOGGEDIN_CMDSET is None:
            from atheriz.commands.loggedin.cmdset import LoggedinCmdSet

            _LOGGEDIN_CMDSET = LoggedinCmdSet()
    return _LOGGEDIN_CMDSET


def get_async_threadpool() -> AsyncThreadPool:
    global _ASYNC_THREAD_POOL
    with _SINGLETON_LOCK:
        if _ASYNC_THREAD_POOL is None:
            from atheriz.globals.asyncthreadpool import AsyncThreadPool

            _ASYNC_THREAD_POOL = AsyncThreadPool(THREADPOOL_LIMIT)
    return _ASYNC_THREAD_POOL


def get_unloggedin_cmdset() -> UnloggedinCmdSet:
    global _UNLOGGEDIN_CMDSET
    with _SINGLETON_LOCK:
        if _UNLOGGEDIN_CMDSET is None:
            from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet

            _UNLOGGEDIN_CMDSET = UnloggedinCmdSet()
    return _UNLOGGEDIN_CMDSET


def get_node_handler() -> NodeHandler:
    global _NODE_HANDLER
    with _SINGLETON_LOCK:
        if _NODE_HANDLER is None:
            from atheriz.globals.node import NodeHandler

            _NODE_HANDLER = NodeHandler()
    return _NODE_HANDLER
