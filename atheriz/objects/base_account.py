from atheriz.singletons.objects import filter_by_type, add_object
from atheriz.utils import get_import_path, ensure_thread_safe
from atheriz.singletons.salt import get_salt
from atheriz.singletons.get import get_unique_id
from atheriz.logger import logger
import hashlib
import atheriz.settings as settings
from threading import Lock, RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

IGNORE_FIELDS = ["lock"]


class Account:
    group_save: bool = False

    def __init__(self):
        self.lock = RLock()
        self.id = -1
        self.name = ""
        self.password = ""
        self.characters = []
        self.is_connected = False
        self.is_banned = False
        self.ban_reason = ""
        self.is_pc = False
        self.is_npc = False
        self.is_item = False
        self.is_account = True
        self.is_deleted = False
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    @classmethod
    def create(cls, name: str, password: str) -> 'Account | None':
        """Create a new account."""
        if not name or not password:
            raise ValueError("Name and password must not be empty.")
        existing = filter_by_type("account", lambda x: x.name == name)
        if existing:
            logger.error(f"Account with this name ({name}) already exists.")
            return None
        account = cls()
        account.id = get_unique_id()
        account.name = name
        account.password = Account.hash_password(password)
        account.characters = []
        account.is_connected = False
        account.is_pc = False
        account.is_npc = False
        account.is_item = False
        account.is_mapable = False
        account.is_container = False
        account.is_tickable = False
        account.is_channel = False
        account.is_account = True
        add_object(account)
        return account

    def at_disconnect(self):
        pass

    def add_character(self, character: Object) -> None:
        """Add a character to the account."""
        with self.lock:
            self.characters.append(character.id)
            
    def remove_character(self, character: Object) -> None:
        """Remove a character from the account."""
        with self.lock:
            self.characters.remove(character.id)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash the account password."""
        return hashlib.sha256(f"{password}{get_salt()}".encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the account password."""
        return self.hash_password(password) == self.password

    def set_password(self, password: str) -> None:
        """Set the account password."""
        self.password = self.hash_password(password)

    def login(self, name: str, password: str) -> bool:
        """Log in to the account."""
        with self.lock:
            if self.name == name and self.check_password(password):
                self.logged_in = True
                return True
            return False

    def __getstate__(self):
        with self.lock:
            return self.__dict__.copy()
    

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()
