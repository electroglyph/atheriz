from atheriz.commands.base_cmd import Command
from prettytable import PrettyTable, TableStyle
from typing import TYPE_CHECKING
from atheriz.singletons.get import get_unloggedin_cmdset

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

class HelpCommand(Command):
    key = "help"
    aliases = ["?"]
    desc = "Show help for commands."
    category = "General"

    def setup_parser(self):
        self.parser.add_argument("command", nargs="?", help="Command to get help on")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        cmdset = get_unloggedin_cmdset()
        
        if not args.command:
            table = PrettyTable()
            table.border = not caller.session.screenreader
            table.header = not caller.session.screenreader
            if not caller.session.screenreader:
                table.set_style(TableStyle.DOUBLE_BORDER)
            table.field_names = ["Category", "Command", "Description"]
            table.align = "l"
            table.max_table_width = caller.session.term_width - 2
            commands = []
            unique_cmds = set(cmdset.commands.values())

            for cmd in unique_cmds:
                if cmd.access(caller) and not cmd.hide:
                    commands.append(cmd)

            commands.sort(key=lambda x: (x.category, x.key))

            for cmd in commands:
                table.add_row([cmd.category, cmd.key, cmd.desc])

            caller.msg("\n" + str(table))
            return

        cmd = cmdset.get(args.command)
        if cmd and cmd.access(caller):
            caller.msg(cmd.print_help())
        else:
            caller.msg("Command not found.")
