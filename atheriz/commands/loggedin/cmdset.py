from atheriz.commands.base_cmdset import CmdSet
from atheriz.commands.loggedin.look import LookCommand
from atheriz.commands.loggedin.none import NoneCommand
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz.commands.loggedin.maze import MazeCommand
from atheriz.commands.loggedin.save import SaveCommand
from atheriz.commands.loggedin.spam import SpamCommand
from atheriz.commands.loggedin.build import BuildCommand
from atheriz.commands.loggedin.exam import ExamineCommand
from atheriz.commands.loggedin.channel import ChannelCommand
from atheriz.commands.loggedin.create import CreateCommand
from atheriz.commands.loggedin.reload import ReloadCommand
from atheriz.commands.loggedin.inventory import InventoryCommand
from atheriz.commands.loggedin.quell import QuellCommand, UnquellCommand
from atheriz.commands.loggedin.say import SayCommand
from atheriz.commands.loggedin.drop import DropCommand
from atheriz.commands.loggedin.put import PutCommand
from atheriz.commands.loggedin.get import GetCommand
from atheriz.commands.loggedin.give import GiveCommand
from atheriz.commands.loggedin.shutdown import ShutdownCommand
from atheriz.commands.unloggedin.screenreader import ScreenReaderCommand
from atheriz.commands.loggedin.help import HelpCommand
from atheriz.commands.loggedin.quit import QuitCommand
from atheriz.commands.loggedin.map import MapCommand
from atheriz.commands.loggedin.emote import EmoteCommand
from atheriz.commands.loggedin.desc import DescCommand
from atheriz.commands.loggedin.set import SetCommand, UnsetCommand
from atheriz.commands.loggedin.delete import DeleteCommand
from atheriz.commands.loggedin.wander import WanderCommand
from atheriz.commands.loggedin.move import MoveCommand
from atheriz.commands.loggedin.time import TimeCommand
from atheriz.commands.loggedin.door import DoorCommand
from atheriz.commands.loggedin.open import OpenCommand
from atheriz.commands.loggedin.open import CloseCommand


class LoggedinCmdSet(CmdSet):
    def __init__(self):
        super().__init__()
        self.add(LookCommand())
        self.add(NoneCommand())
        self.add(ExitCommand())
        self.add(MazeCommand())
        self.add(SaveCommand())
        self.add(SpamCommand())
        self.add(BuildCommand())
        self.add(ExamineCommand())
        self.add(ChannelCommand())
        self.add(CreateCommand())
        self.add(ReloadCommand())
        self.add(InventoryCommand())
        self.add(QuellCommand())
        self.add(UnquellCommand())
        self.add(SayCommand())
        self.add(DropCommand())
        self.add(PutCommand())
        self.add(GetCommand())
        self.add(GiveCommand())
        self.add(ShutdownCommand())
        self.add(ScreenReaderCommand())
        self.add(HelpCommand())
        self.add(QuitCommand())
        self.add(MapCommand())
        self.add(EmoteCommand())
        self.add(DescCommand())
        self.add(SetCommand())
        self.add(UnsetCommand())
        self.add(DeleteCommand())
        self.add(WanderCommand())
        self.add(MoveCommand())
        self.add(TimeCommand())
        self.add(DoorCommand())
        self.add(OpenCommand())
        self.add(CloseCommand())
