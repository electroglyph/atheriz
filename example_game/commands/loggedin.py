from atheriz.commands.loggedin.cmdset import LoggedinCmdSet as BaseLoggedinCmdSet


class LoggedinCmdSet(BaseLoggedinCmdSet):
    """Custom LoggedinCmdSet class. Override methods below to customize behavior."""
    def __init__(self):
        super().__init__()
        # self.add(MyLoggedinCommand())
