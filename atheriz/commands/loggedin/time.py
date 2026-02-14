from atheriz.commands.base_cmd import Command
from atheriz.singletons.get import get_game_time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class TimeCommand(Command):
    key = "time"
    desc = "Show the current time."
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.msg(get_game_time().get_time()["formatted"])
