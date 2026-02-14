from atheriz.commands.base_cmd import Command
from atheriz.reloader import reload_game_logic
from atheriz.logger import logger
from atheriz.singletons.get import get_server_channel
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
        if channel:
            channel.msg(f"{result}")
        else:
            caller.msg(f"{result}")
