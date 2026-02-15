from typing import Any, Callable
import argparse
import shlex
from atheriz.utils import get_import_path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.session import Session
    from atheriz.objects.base_obj import Object
    from atheriz.websocket import Connection


class CommandError(Exception):
    """Raised when argument parsing fails or help is requested."""

    pass


class GameArgumentParser(argparse.ArgumentParser):
    """
    Subclass of ArgumentParser that raises exceptions instead of exiting.
    """

    def error(self, message):
        """Override error to raise exception instead of exiting."""
        raise CommandError(message)

    def print_help(self, file=None):
        """Override print_help to raise exception with help text."""
        # We raise the help message as an error so it can be caught and returned
        raise CommandError(self.format_help())

    def print_usage(self, file=None):
        """Override print_usage to raise exception with usage text."""
        raise CommandError(self.format_usage())

    # pyrefly: ignore
    def exit(self, status=0, message=None):
        """Override exit to prevent sys.exit."""
        if message:
            raise CommandError(message)


class Command:
    """
    Base command class.

    Attributes:
        key (str): The primary keyword to invoke this command.
        aliases (list[str]): Alternate keywords.
        description (str): Brief description of the command.
    """

    key: str = "base"
    aliases: list[str] = []
    desc: str = "Base command"
    category: str = "General"
    tag: str = ""
    hide: bool = False
    use_parser: bool = True

    def access(self, caller: Object | Connection) -> bool:
        """
        Override this method to implement access control.

        Args:
            caller: The object/player calling the command.

        Returns:
            bool: True if the caller has access, False otherwise.

        Separate locks aren't implemented for commands since all commands are already custom classes
        it's just as easy to implement access control in the command class itself.
        """
        return True

    def __init__(self):
        self._parser = None

    @property
    def parser(self) -> GameArgumentParser | None:
        if self._parser is None:
            if self.use_parser:
                self._parser = GameArgumentParser(
                    prog=self.key, description=self.desc, add_help=True
                )
                self.setup_parser()
        return self._parser

    @parser.setter
    def parser(self, value):
        self._parser = value

    def setup_parser(self):
        """
        Override this method to add arguments to self.parser.
        Example:
            self.parser.add_argument("target", help="Target name")
        """
        pass

    def print_help(self):
        """
        Override this method to implement help text.
        """
        a = [x for x in self.aliases]
        a.insert(0, self.key)
        return self.parser.format_help() + f"\naliases: {', '.join(a)}\n"

    def run(self, caller: Object | Connection, args) -> Any:
        """
        Override this method to implement the command logic.

        Args:
            caller: The object/player calling the command.
            args: The parsed namespace from argparse.
        """
        pass

    def execute(
        self, caller: Object | Connection, args_string: str
    ) -> (
        tuple[Callable[[Object | Connection, Any], None], Object | Connection, Any]
        | tuple[None, None, None]
    ):
        """
        Parses arguments and runs the command.

        Args:
            caller: The object/player calling the command.
            args_string: The string containing the arguments (command name stripped).

        Returns:
            tuple[Callable[[Object | Connection, Any], None], Object | Connection, Any]: the run function, caller, and the parsed arguments
        """
        if not self.use_parser:
            return self.run, caller, args_string
        # Use shlex to split arguments respecting quotes
        # e.g. 'look "my stuff"' -> ['look', 'my stuff']
        if not args_string:
            arg_list = []
        else:
            arg_list = shlex.split(args_string, posix=False)
        try:
            parsed_args = self.parser.parse_args(arg_list)
        except CommandError:
            self.print_help()
            return None, None, None
        return self.run, caller, parsed_args

    def __getstate__(self):
        state = self.__dict__.copy()
        state["__import_path__"] = get_import_path(self)
        del state["_parser"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        if self.use_parser:
            self.parser = GameArgumentParser(
                prog=self.key, description=self.desc, add_help=True
            )
            self.setup_parser()
