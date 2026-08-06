from __future__ import annotations
from atheriz.commands.base_cmdset import CmdSet
from atheriz.commands.unloggedin.connect import ConnectCommand
from atheriz.commands.unloggedin.create import CreateCommand
from atheriz.commands.unloggedin.guest import GuestCommand
from atheriz.commands.unloggedin.new import NewCharacterCommand
from atheriz.commands.unloggedin.none import NoneCommand
from atheriz.commands.unloggedin.screenreader import ScreenReaderCommand
from atheriz.commands.unloggedin.help import HelpCommand
from atheriz.commands.unloggedin.quit import QuitCommand
import atheriz.settings as settings

class UnloggedinCmdSet(CmdSet):
    def __init__(self):
        super().__init__()
        self.add(ConnectCommand())
        if settings.ACCOUNT_CREATION_ENABLED:
            self.add(CreateCommand())
        if settings.CHAR_CREATION_ENABLED:
            self.add(NewCharacterCommand())
        self.add(GuestCommand())
        self.add(NoneCommand())
        self.add(ScreenReaderCommand())
        self.add(HelpCommand())
        self.add(QuitCommand())
