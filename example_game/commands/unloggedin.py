from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet as BaseUnloggedinCmdSet


class UnloggedinCmdSet(BaseUnloggedinCmdSet):
    """Custom UnloggedinCmdSet class. Override methods below to customize behavior."""
    def __init__(self):
        super().__init__()
        # self.add(MyUnloggedinCommand())
