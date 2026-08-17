from .objects import load_objects
from .get import get_async_threadpool, get_map_handler, get_node_handler, get_server_channel, get_async_ticker, get_game_time
from atheriz.globals.objects import save_objects, load_objects
from atheriz.globals.autosave import start_autosave, stop_autosave
from atheriz.database_setup import get_database
import atheriz.settings as settings
from atheriz.logger import logger
from atheriz.utils import msg_all
import traceback
import threading
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from atheriz.objects.base_channel import Channel
    from atheriz.objects.base_obj import Object


_shutdown_lock = threading.Lock()
_shutdown_completed = False


def _shutdown_step(name: str, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.error(f"Shutdown step '{name}' failed:\n{traceback.format_exc()}")



def do_startup():
    global _shutdown_completed
    with _shutdown_lock:
        _shutdown_completed = False
    load_objects()
    get_async_threadpool()
    get_map_handler()
    get_node_handler()
    get_async_ticker()
    try:
        import server_events
    except ImportError:
        import atheriz.server_events as server_events
    server_events.at_server_start()
    if settings.TIME_SYSTEM_ENABLED:
        get_game_time().start()
    start_autosave()


def do_shutdown():
    global _shutdown_completed
    with _shutdown_lock:
        if _shutdown_completed:
            logger.info("Shutdown already completed; skipping.")
            return
        _shutdown_completed = True
    channel: Channel | None = get_server_channel()
    if channel:
        channel.msg("Server is shutting down!")
    logger.info("Starting shutdown sequence...")
    try:
        import server_events
    except ImportError:
        import atheriz.server_events as server_events
    _shutdown_step("at_server_stop", server_events.at_server_stop)
    _shutdown_step("stop_autosave", stop_autosave)
    _shutdown_step("ticker_stop", get_async_ticker().stop)
    _shutdown_step("threadpool_stop", get_async_threadpool().stop, True, 10)
    if settings.AUTOSAVE_ON_SHUTDOWN:
        _shutdown_step("save_objects", save_objects)
        _shutdown_step("map_save", get_map_handler().save)
        _shutdown_step("node_save", get_node_handler().save)
    _shutdown_step("msg_all", msg_all, "Server is shutting down NOW!")
    logger.info("Shutdown sequence completed.")
    if settings.TIME_SYSTEM_ENABLED:
        _shutdown_step("game_time_stop", get_game_time().stop)
    # the pool and ticker are single-use: anything that touches them after
    # shutdown must get a fresh one (e.g. a server booted and torn down
    # inside a test process). This must come last: earlier steps (e.g.
    # GameTime.stop) still resolve the live singletons.
    import atheriz.globals.get as get_singleton
    get_singleton._ASYNC_THREAD_POOL = None
    get_singleton._ASYNC_TICKER = None
    _shutdown_step("db_close", get_database().close)


def do_reload():
    channel: Channel | None = get_server_channel()
    if channel:
        channel.msg("Server is reloading...")
    logger.info("Starting reload sequence...")
    try:
        import server_events
        import importlib
        importlib.reload(server_events)
    except ImportError:
        import atheriz.server_events as server_events
    server_events.at_server_reload()
    if settings.TIME_SYSTEM_ENABLED:
        get_game_time().stop()
    stop_autosave()
    get_async_ticker().clear()
    if settings.TIME_SYSTEM_ENABLED:
        get_game_time().start()
    if settings.AUTOSAVE_ON_RELOAD:
        save_objects()
        get_map_handler().save()
        get_node_handler().save()
    start_autosave()
    channel: Channel | None = get_server_channel()
    if channel:
        channel.msg("Server reloaded")
    logger.info("Reload sequence completed.")
