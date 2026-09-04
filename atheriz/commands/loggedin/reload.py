from __future__ import annotations
from atheriz.commands.base_cmd import Command
from atheriz.reloader import reload_game_logic
from atheriz.logger import logger
from atheriz.globals.get import get_server_channel, get_async_ticker
from atheriz.globals.startstop import _reregister_ticks
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel

try:
    import server_events
    import importlib

    importlib.reload(server_events)
except ImportError:
    import atheriz.server_events as server_events


class ReloadCommand(Command):
    key = "reload"
    desc = "Reload game logic and modules."
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_superuser

    # pyrefly: ignore
    def run(self, caller: Object, args):
        channel: Channel | None = get_server_channel()
        if channel:
            channel.msg("Server is reloading...")

        server_events.at_server_reload()

        logger.info(f"Reload triggered by {caller.name} ({caller.id})")
        result = reload_game_logic()
        # Refresh ticker registrations so the new tick code actually runs
        # (clear drops stale pre-reload bound methods; re-register captures
        # the post-reload ones). Mirrors do_reload().
        try:
            get_async_ticker().clear()
            _reregister_ticks()
        except Exception as e:
            logger.error(f"Tick refresh after reload failed: {e}")
        if channel:
            channel.msg(f"{result}")
        else:
            caller.msg(f"{result}")
