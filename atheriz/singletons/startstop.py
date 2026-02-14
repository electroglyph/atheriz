from .objects import load_files
from .get import get_async_threadpool, get_map_handler, get_node_handler, get_server_channel, get_async_ticker, get_game_time
from atheriz.singletons.objects import filter_by, _ALL_OBJECTS, _ALL_OBJECTS_LOCK
from atheriz.objects.persist import save
import atheriz.settings as settings
from atheriz.logger import logger
from atheriz.utils import msg_all
from typing import TYPE_CHECKING
from atheriz.server_events import at_server_start, at_server_stop, at_server_reload
if TYPE_CHECKING:
    from atheriz.objects.base_channel import Channel
    from atheriz.objects.base_obj import Object


def do_startup():
    load_files()
    get_async_threadpool()
    get_map_handler()
    get_node_handler()
    get_async_ticker()
    at_server_start()
    if settings.TIME_SYSTEM_ENABLED:
        get_game_time().start()


def do_shutdown():
    channel: Channel | None = get_server_channel()
    if channel:
        channel.msg("Server is shutting down!")
    logger.info("Starting shutdown sequence...")
    at_server_stop()
    if settings.AUTOSAVE_ON_SHUTDOWN:
        with _ALL_OBJECTS_LOCK:
            objs = list(_ALL_OBJECTS.values())
        save(objs)
        get_map_handler().save()
        get_node_handler().save()
    get_async_ticker().stop()
    get_async_threadpool().stop(False)
    msg_all("Server is shutting down NOW!")
    logger.info("Shutdown sequence completed.")
    if settings.TIME_SYSTEM_ENABLED:
        get_game_time().stop()


def do_reload():
    channel: Channel | None = get_server_channel()
    if channel:
        channel.msg("Server is reloading...")
    logger.info("Starting reload sequence...")
    get_async_ticker().clear()
    at_server_reload()
    if settings.AUTOSAVE_ON_RELOAD:
        with _ALL_OBJECTS_LOCK:
            objs = list(_ALL_OBJECTS.values())
        save(objs)
        get_map_handler().save()
        get_node_handler().save()
    if channel:
        channel.msg("Server reloaded")
    logger.info("Reload sequence completed.")
