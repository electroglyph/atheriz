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
        del unused
        if not self.at_delete(caller):
            return False
            
        ops = [self.get_del_ops()]
        delete_objects(ops)
        remove_object(self)
        self.is_deleted = True
        return True

    def at_pre_puppet(self, character: Object) -> bool:
        """Called before a character is puppeted, return False to cancel puppeting."""
        return True

    def at_delete(self, caller: Object | None = None) -> bool:
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
            for cls in type(self).mro():
                # remove excluded keys
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            state.pop("lock", None)
            return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = RLock()
