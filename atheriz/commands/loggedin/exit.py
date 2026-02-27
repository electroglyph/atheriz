from atheriz.commands.base_cmd import Command
from atheriz.singletons.objects import get
from atheriz.singletons.get import get_node_handler
from atheriz.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.session import Session
    from atheriz.objects.base_obj import Object


class ExitCommand(Command):
    key = "exit"
    aliases: list[str] | None = None
    desc = "bleh"
    caller_id: int = -1
    location: tuple[str, int, int, int] | None = None
    destination: tuple[str, int, int, int] | None = None
    tag = "exits"
    name: str = ""
    # don't show in help list
    hide = True
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Object | Session, args):
        self.do_move()

    def do_move(self):
        nh = get_node_handler()
        c = get(self.caller_id)
        if c:
            c: Object = c[0]
        else:
            logger.error(f"Exit command with invalid caller. id = {self.caller_id}, destination = {self.destination}, location = {self.location}, name = {self.name}")
            return
        if not self.location or not self.destination:
            logger.error(f"invalid Exit command. id = {self.caller_id}, destination = {self.destination}, location = {self.location}, name = {self.name}")
            return
        dest = nh.get_node(self.destination)
        if not dest:
            logger.error(f"Error getting destination node for: {self.destination}")
            return
        d = nh.get_doors(self.location)
        if d:
            door = d.get(self.name)
            if door:
                if door.closed and door.try_open(c):
                    if c.move_to(dest, self.name):
                        door.try_close(c)
                    return
                elif not door.closed:
                    c.move_to(dest, self.name)
                    return
                else:
                    return
        c.move_to(dest, self.name)
