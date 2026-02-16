from atheriz.commands.base_cmdset import CmdSet
from atheriz.commands.unloggedin.connect import ConnectCommand
from atheriz.commands.unloggedin.none import NoneCommand
from atheriz.commands.unloggedin.screenreader import ScreenReaderCommand
from atheriz.commands.unloggedin.help import HelpCommand

class UnloggedinCmdSet(CmdSet):
    def __init__(self):
        super().__init__()
        self.add(ConnectCommand())
        self.add(NoneCommand())
        self.add(ScreenReaderCommand())
        self.add(HelpCommand())
