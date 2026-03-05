from __future__ import annotations
from atheriz.singletons.objects import add_object, remove_object, filter_by, delete_objects
from atheriz.utils import ensure_thread_safe
from atheriz.singletons.salt import get_salt
from atheriz.singletons.get import get_unique_id
from atheriz.logger import logger
import hashlib
import atheriz.settings as settings
from threading import RLock
from atheriz.objects.base_flags import Flags
from atheriz.objects.base_db_ops import DbOps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

IGNORE_FIELDS = ["lock"]


class Account(Flags, DbOps):
    group_save: bool = False

    def __init__(self):
        super().__init__()
        self.lock = RLock()
        self.id = -1
        self.name = ""
        self.password = ""
        self.characters = []
        self.is_banned = False
        self.ban_reason = ""
        self.is_account = True
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    @classmethod
    def create(cls, name: str, password: str) -> "Account | None":
        """Create a new account."""
        if not name or not password:
            raise ValueError("Name and password must not be empty.")
        existing = filter_by(lambda x: x.is_account and x.name == name)
        if existing:
            logger.error(f"Account with this name ({name}) already exists.")
            return None
        account = cls()
        account.id = get_unique_id()
        account.name = name
        account.password = Account.hash_password(password)
        account.characters = []
        add_object(account)
        account.at_create()
        return account

    def delete(self, caller: Object | None = None, unused: bool = True) -> bool:
        """
        Delete this account from the game entirely.
        
        Args:
            caller (Object | None, optional): The object executing the deletion. Defaults to None.
            unused (bool, optional): Unused parameter for API compatibility. Defaults to True.
            
        Returns:
            bool: True if the account was successfully deleted, False if aborted.
        """
        del unused
        if not self.at_delete(caller):
            return False
            
        ops = [self.get_del_ops()]
        delete_objects(ops)
        remove_object(self)
        self.is_deleted = True
        return True

    def at_pre_puppet(self, character: Object) -> bool:
        """
        Called before a character is puppeted by this account.
        
        Args:
            character (Object): The character object to puppet.
            
        Returns:
            bool: True to allow puppeting, False to cancel.
        """
        return True

    def at_delete(self, caller: Object | None = None) -> bool:
        """
        Called before the account is deleted.
        
        Args:
            caller (Object | None, optional): The object executing the command. Defaults to None.
            
        Returns:
            bool: True to proceed with deletion, False to stop.
        """
        return True

    def at_create(self):
        """
        Called after a new account is successfully created.
        """
        pass

    def at_disconnect(self):
        """
        Called when a session associated with this account disconnects.
        """
        pass

    def add_character(self, character: Object) -> None:
        """
        Add a character's ID to the list of characters owned by this account.
        
        Args:
            character (Object): The character to add.
        """
        with self.lock:
            self.characters.append(character.id)

    def remove_character(self, character: Object) -> None:
        """
        Remove a character's ID from the list of characters owned by this account.
        
        Args:
            character (Object): The character to remove.
        """
        with self.lock:
            self.characters.remove(character.id)

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash the given plaintext password using the system salt.
        
        Args:
            password (str): The plaintext password to hash.
            
        Returns:
            str: The SHA-256 hashed password string.
        """
        return hashlib.sha256(f"{password}{get_salt()}".encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        """
        Check if the provided plaintext password matches the account's hashed password.
        
        Args:
            password (str): The plaintext password to test.
            
        Returns:
            bool: True if the passwords match, False otherwise.
        """
        return self.hash_password(password) == self.password

    def set_password(self, password: str) -> None:
        """
        Update and hash the account's password.
        
        Args:
            password (str): The new plaintext password.
        """
        self.password = self.hash_password(password)

    def login(self, name: str, password: str) -> bool:
        """
        Attempt to log in to the account with given credentials.
        
        Args:
            name (str): The provided account name.
            password (str): The plaintext password to verify.
            
        Returns:
            bool: True on successful authentication, False otherwise.
        """
        with self.lock:
            if self.name == name and self.check_password(password):
                self.logged_in = True
                return True
            return False

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            for cls in type(self).mro():
                # remove excluded keys
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            state.pop("lock", None)
            return state

    def __setstate__(self, state):
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)
