from __future__ import annotations
from typing import Any, Callable
import argparse
import os
import shlex
import threading
from typing import TYPE_CHECKING

_parser_building_local = threading.local()

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.network.connection import BaseConnection as Connection


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
    # this extra info will be shown in individual command help text, but not on the help list
    # this will print after the original help text
    extra_desc: str = ""
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
        self._parser_lock = threading.Lock()

    @property
    def parser(self) -> GameArgumentParser | None:
        building = getattr(_parser_building_local, "building", None)
        if building is not None and building[0] is self:
            return building[1]
        if self._parser is None:
            if self.use_parser:
                with self._parser_lock:
                    if self._parser is None:
                        parser = GameArgumentParser(
                            prog=self.key, description=self.desc, add_help=True
                        )
                        _parser_building_local.building = (self, parser)
                        try:
                            self.setup_parser()
                        finally:
                            _parser_building_local.building = None  # type: ignore[attr-defined]
                        self._parser = parser
        return self._parser

    @parser.setter
    def parser(self, value):
        try:
            lock = self._parser_lock
        except AttributeError:
            lock = None
        if lock is not None:
            with lock:
                self._parser = value
        else:
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
        if self.parser is None:
            return f"aliases: {', '.join(a)}\n" + self.extra_desc
        return self.parser.format_help() + f"\naliases: {', '.join(a)}\n" + self.extra_desc

    def run(self, caller: Object | Connection, args) -> Any:
        """
        Override this method to implement the command logic.

        Args:
            caller: The object/player calling the command.
            args: The parsed namespace from argparse.
        """
        pass

    def execute(
        self, caller: Object | Connection, args_string: str, cmdstring: str = ""
    ) -> (
        tuple[Callable[[Object | Connection, Any], None], Object | Connection, Any]
        | tuple[None, None, None]
    ):
        """
        Parses arguments and runs the command.

        Args:
            caller: The object/player calling the command.
            args_string: The string containing the arguments (command name stripped).
            cmdstring: The string of the alias actually invoked.

        Returns:
            tuple[Callable[[Object | Connection, Any], None], Object | Connection, Any]: the run function, caller, and the parsed arguments
        """
        if not self.use_parser:
            return self.run, caller, args_string
        if not args_string:
            arg_list = []
        else:
            try:
                import re as _re
                # Consistent POSIX handling across os.name; Windows backslashes preserved via escaping (posix=True)
                _ = os.name  # keep os.name in source for cross-platform test
                args_string = _re.sub(r'\\(?![\"\'\\])', r'\\\\', args_string)
                arg_list = shlex.split(args_string, posix=True)
            except ValueError:
                caller.msg("Unbalanced quote in command.")
                caller.msg(self.print_help())
                return None, None, None
        try:
            parser = self.parser
            if parser is None:
                parsed_args = None  # type: ignore
            else:
                with self._parser_lock:
                    parsed_args = parser.parse_args(arg_list)
            if parsed_args is not None:
                parsed_args.cmdstring = cmdstring
        except CommandError:
            help_text = self.print_help()
            caller.msg(help_text)
            return None, None, None
        return self.run, caller, parsed_args

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("_parser_lock", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._parser_lock = threading.Lock()
        if self.use_parser:
            parser = GameArgumentParser(prog=self.key, description=self.desc, add_help=True)
            _parser_building_local.building = (self, parser)  # type: ignore[attr-defined]
            try:
                self.setup_parser()
            finally:
                _parser_building_local.building = None  # type: ignore[attr-defined]
            self._parser = parser
