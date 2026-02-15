from typing import TYPE_CHECKING
from threading import Lock, RLock
from atheriz.logger import logger
from atheriz.utils import get_import_path, instance_from_string

if TYPE_CHECKING:
    from atheriz.commands.base_cmd import Command


class CmdSet:
    def __init__(self):
        self.lock = RLock()
        self.commands: dict[str, Command] = {}

    def get_all(self) -> list[Command]:
        """Get all commands in the command set."""
        with self.lock:
            return list(self.commands.values())

    def add(self, command: Command, tag: str | None = None):
        """Add a command to the command set. If you overwrite a command, it's on you to figure out how/if to put it back"""
        if tag is not None:
            command.tag = tag
        with self.lock:
            if command.key in self.commands:
                logger.warning(f"Overwriting command {command.key}")
            self.commands[command.key] = command
            if command.aliases:
                for alias in command.aliases:
                    if alias in self.commands:
                        logger.warning(f"Overwriting command alias {alias}")
                    self.commands[alias] = command

    def adds(self, commands: list[Command], tag: str | None = None):
        """Add a command to the command set. If you overwrite a command, it's on you to figure out how/if to put it back"""
        if tag is not None:
            for command in commands:
                command.tag = tag
        with self.lock:
            for command in commands:
                if command.key in self.commands:
                    logger.warning(f"Overwriting command {command.key}")
                self.commands[command.key] = command
                if command.aliases:
                    for alias in command.aliases:
                        if alias in self.commands:
                            logger.warning(f"Overwriting command alias {alias}")
                        self.commands[alias] = command

    def remove(self, command: Command):
        """Remove a command from the command set."""
        with self.lock:
            self.commands.pop(command.key, None)
            if command.aliases:
                for alias in command.aliases:
                    self.commands.pop(alias, None)

    def remove_by_tag(self, tag: str):
        """Remove a command from the command set by tag."""
        to_del = []
        with self.lock:
            for key, command in self.commands.items():
                if command.tag == tag:
                    to_del.append(key)
            for key in to_del:
                del self.commands[key]

    def get(self, command: str) -> Command | None:
        """Get a command from the command set."""
        with self.lock:
            return self.commands.get(command)

    def get_keys(self) -> list[str]:
        """Get a list of all command keys."""
        with self.lock:
            return list(self.commands.keys())

    def __getstate__(self):
        with self.lock:
            return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()