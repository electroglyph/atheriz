from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.network.connection import BaseConnection as Connection


class QuitCommand(Command):
    key = "quit"
    desc = "Quit."
    use_parser = False
    aliases = ["exit", "quit", "logout", "disconnect"]

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.msg("Goodbye!")
        connection: Connection = caller.session.connection
        connection.close()
