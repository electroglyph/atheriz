from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection


class ScreenReaderCommand(Command):
    key = "screenreader"
    aliases = ["sr"]
    category = "Communication"
    desc = "Toggle screenreader mode."
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Connection, args):
        caller.session.screenreader = not caller.session.screenreader
        caller.session.connection.send_command("screenreader", caller.session.screenreader)
