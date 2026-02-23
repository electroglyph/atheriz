from atheriz.commands.base_cmd import Command
from prettytable import PrettyTable, TableStyle
from typing import TYPE_CHECKING
from atheriz.singletons.get import get_loggedin_cmdset

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

NO_PARSER_TEMPLATE = """
{description}

Aliases: {aliases}
"""

class HelpCommand(Command):
    key = "help"
    aliases = ["?"]
    desc = "Show help for commands."
    category = "General"

    def setup_parser(self):
        self.parser.add_argument("command", nargs="?", help="Command to get help on")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        cmdset = get_loggedin_cmdset()
        loc = caller.location
        if not args:
            table = PrettyTable()
            table.border = not caller.session.screenreader
            table.header = not caller.session.screenreader
            if not caller.session.screenreader:
                table.set_style(TableStyle.DOUBLE_BORDER)
            table.field_names = ["Category", "Command", "Description"]
            table.align = "l"
            table.max_table_width = caller.session.term_width - 2
            commands = []
            unique_cmds = set(cmdset.get_all())
            command_text = ""

            for cmd in unique_cmds:
                if cmd.access(caller) and not cmd.hide:
                    commands.append(cmd)

            if commands:
                commands.sort(key=lambda x: (x.category, x.key))
                for cmd in commands:
                    table.add_row([cmd.category, cmd.key, cmd.desc])
                command_text = str(table)
            else:
                command_text = "No system commands found."
            local_commands = []
            local_text = ""
            if loc:
                for o in loc.contents:
                    if o.external_cmdset:
                        for cmd in o.external_cmdset.get_all():
                            if cmd.access(caller) and not cmd.hide:
                                local_commands.append(cmd)
            for o in caller.contents:
                if o.external_cmdset:
                    for cmd in o.external_cmdset.get_all():
                        if cmd.access(caller) and not cmd.hide:
                            local_commands.append(cmd)
            if local_commands:
                local_commands.sort(key=lambda x: (x.category, x.key))
                table2 = PrettyTable()
                table2.border = not caller.session.screenreader
                table2.header = not caller.session.screenreader
                if not caller.session.screenreader:
                    table2.set_style(TableStyle.DOUBLE_BORDER)
                table2.field_names = ["Category", "Command", "Description"]
                table2.align = "l"
                table2.max_table_width = caller.session.term_width - 2
                for cmd in local_commands:
                    table2.add_row([cmd.category, cmd.key, cmd.desc])
                local_text = str(table2)
            
            caller.msg(f"{command_text}\nLocal commands:\n{local_text}") if local_text else caller.msg(command_text)
            return

        def print_help(cmd):
            if cmd.parser:
                return cmd.print_help()
            else:
                return NO_PARSER_TEMPLATE.format(
                    description=cmd.desc,
                    aliases=f"{cmd.key}, " + ", ".join(cmd.aliases) if cmd.aliases else f"{cmd.key}"
                )
        cmd = cmdset.get(args.command)
        if cmd and cmd.access(caller) and not cmd.hide:
            caller.msg(print_help(cmd))
            return
        else:
            if loc:
                for o in loc.contents:
                    if o.external_cmdset:
                        for cmd in o.external_cmdset.get_all():
                            if cmd.key == args.command and cmd.access(caller) and not cmd.hide:
                                caller.msg(print_help(cmd))
                                return
            for o in caller.contents:
                if o.external_cmdset:
                    for cmd in o.external_cmdset.get_all():
                        if cmd.key == args.command and cmd.access(caller) and not cmd.hide:
                            caller.msg(print_help(cmd))
                            return
            caller.msg("Command not found.")
