from __future__ import annotations
from typing import TYPE_CHECKING
from threading import RLock
from atheriz.logger import logger

if TYPE_CHECKING:
    from atheriz.commands.base_cmd import Command


class CmdSet:
    def __init__(self):
        self.lock = RLock()
        self.commands: dict[str, Command] = {}

    def get_all(self) -> list[Command]:
        """
        Extract all commands currently active in this command set.

        Returns:
            list[Command]: A list of all Command instances.
        """
        with self.lock:
            return list(self.commands.values())

    def add(self, command: Command, tag: str | None = None) -> None:
        """
        Merge a single Command instance into this command set. 
        If a command with the same key or alias already exists, it is overwritten.

        Args:
            command (Command): The command object to add.
            tag (str | None, optional): An optional tag to categorize the command (e.g. "exits"). 
                Defaults to None.
        """
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

    def adds(self, commands: list[Command], tag: str | None = None) -> None:
        """
        Merge multiple Command instances into this command set simultaneously.
        Any commands with duplicate keys or aliases will overwrite pre-existing ones.

        Args:
            commands (list[Command]): A list of Command objects to add.
            tag (str | None, optional): An optional tag to apply to all added commands. 
                Defaults to None.
        """
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

    def remove(self, command: Command) -> None:
        """
        Remove a specific Command instance from this command set, including its aliases.

        Args:
            command (Command): The command object to remove.
        """
        with self.lock:
            self.commands.pop(command.key, None)
            if command.aliases:
                for alias in command.aliases:
                    self.commands.pop(alias, None)

    def remove_by_tag(self, tag: str) -> None:
        """
        Remove all commands matching a specific tag string from this command set.

        Args:
            tag (str): The tag identifier (e.g., "exits").
        """
        to_del = []
        with self.lock:
            for key, command in self.commands.items():
                if command.tag == tag:
                    to_del.append(key)
            for key in to_del:
                del self.commands[key]

    def get(self, command: str) -> Command | None:
        """
        Retrieve a Command instance by its key or alias.

        Args:
            command (str): The key or alias to search for.

        Returns:
            Command | None: The matching Command object, or None if not found.
        """
        with self.lock:
            return self.commands.get(command)

    def get_keys(self) -> list[str]:
        """
        Retrieve a list of all raw command keywords and aliases currently registered in this set.

        Returns:
            list[str]: A list of command keys.
        """
        with self.lock:
            return list(self.commands.keys())

    def __getstate__(self):
        with self.lock:
            return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()