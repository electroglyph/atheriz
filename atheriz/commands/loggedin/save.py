from atheriz.commands.base_cmd import Command
from atheriz.singletons.objects import save_objects
from atheriz.singletons.get import get_map_handler, get_node_handler, get_game_time
import atheriz.settings as settings
from typing import TYPE_CHECKING
import time

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class SaveCommand(Command):
    key = "save"
    category = "Admin"
    desc = "Save all the things."
    hide = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_superuser

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.msg("Saving...")
        start = time.time()
        save_objects()
        get_map_handler().save()
        get_node_handler().save()
        if settings.TIME_SYSTEM_ENABLED:
            get_game_time().save()
        caller.msg(f"Saved in {(time.time() - start) * 1000} milliseconds.")
