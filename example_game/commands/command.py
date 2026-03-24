from atheriz.commands.base_cmd import Command as BaseCommand


class Command(BaseCommand):
    """Custom Command class. Override methods below to customize behavior."""

    def run(self, caller, args):
        """Override this method to implement the command logic."""
        pass

    def setup_parser(self):
        """Override this method to add arguments to self.parser."""
        pass
