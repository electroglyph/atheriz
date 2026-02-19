import dill
from atheriz.singletons.objects import add_object, remove_object, filter_by
from atheriz.utils import ensure_thread_safe
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
        self.is_modified = True
        self.is_pc = False
        self.is_npc = False
        self.is_item = False
        self.is_account = True
        self.is_deleted = False
        self.is_mapable = False
        self.is_container = False
        self.is_tickable = False
        self.is_channel = False
        self.is_node = False
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

    def get_save_ops(self) -> tuple[str, tuple]:
        """
        Returns a tuple of (sql, params) for saving this object.
        """
        sql = "INSERT OR REPLACE INTO objects (id, data) VALUES (?, ?)"
        with self.lock:
            object.__setattr__(self, "is_modified", False)
            params = (self.id, dill.dumps(self))
        return sql, params

    def delete(self, caller: Object, unused: bool) -> int:
        del unused
        if not self.at_delete(caller):
            return 0
        self.is_deleted = True
        remove_object(self)
        return 1

    def at_pre_puppet(self, character: Object) -> bool:
        """Called before a character is puppeted, return False to cancel puppeting."""
        return True

    def at_delete(self, caller: Object) -> bool:
        """Called before an object is deleted, return False to cancel deletion."""
        return True

    def at_create(self):
        """Called after an object is created."""
        pass

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
            state = self.__dict__.copy()
            state.pop("lock", None)
            return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()
