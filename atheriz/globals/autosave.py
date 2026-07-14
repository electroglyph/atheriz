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
    failures = []
    for name, fn in [
        ("objects", save_objects),
        ("map", lambda: get_map_handler().save()),
        ("node", lambda: get_node_handler().save()),
    ]:
        try:
            fn()
        except Exception:
            failures.append(name)
            logger.error(f"Autosave failed for {name}:\n{traceback.format_exc()}")
    if settings.TIME_SYSTEM_ENABLED:
        try:
            from atheriz.globals.get import get_game_time
            get_game_time().save()
        except Exception:
            failures.append("time")
            logger.error(f"Autosave failed for time:\n{traceback.format_exc()}")
    if failures:
        channel = get_server_channel()
        if channel:
            channel.msg(f"Autosave failed for: {', '.join(failures)}")
    else:
        logger.info("Autosave completed.")
        channel = get_server_channel()
        if channel:
            channel.msg("Autosave completed.")


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
