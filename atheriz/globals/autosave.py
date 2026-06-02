from atheriz.logger import logger
from atheriz.globals.get import (
    get_async_ticker,
    get_map_handler,
    get_node_handler,
    get_server_channel,
)
from atheriz.globals.objects import save_objects
import atheriz.settings as settings
import traceback

_autosave_started = False


def _interval_seconds() -> float:
    return float(settings.AUTOSAVE_MINUTES) * 60.0


def autosave_tick() -> None:
    try:
        save_objects()
        get_map_handler().save()
        get_node_handler().save()
        if settings.TIME_SYSTEM_ENABLED:
            from atheriz.globals.get import get_game_time

            get_game_time().save()
        logger.info("Autosave completed.")
        channel = get_server_channel()
        if channel:
            channel.msg("Autosave completed.")
    except Exception:
        tb = traceback.format_exc()
        logger.error(f"Autosave failed:\n{tb}")
        channel = get_server_channel()
        if channel:
            channel.msg(f"Autosave failed:\n{tb}")


def start_autosave() -> None:
    global _autosave_started
    if not settings.AUTOSAVE_MINUTES or _autosave_started:
        return
    interval = _interval_seconds()
    get_async_ticker().add_coro(autosave_tick, interval)
    _autosave_started = True
    logger.info(f"Autosave enabled: every {settings.AUTOSAVE_MINUTES} minutes.")


def stop_autosave() -> None:
    global _autosave_started
    if not _autosave_started:
        return
    interval = _interval_seconds()
    get_async_ticker().remove_coro(autosave_tick, interval)
    _autosave_started = False
