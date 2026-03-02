from atheriz.objects.base_account import Account as BaseAccount
from .flags import Flags
from .db_ops import DbOps


class Account(BaseAccount, Flags, DbOps):
    """Custom Account class. Override methods below to customize behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def at_create(self):
        """Called after an object is created."""
        pass

    def at_delete(self, caller=None):
        """Called before an object is deleted, return False to cancel deletion."""
        return super().at_delete(caller)

    def at_disconnect(self):
        pass

    def at_pre_puppet(self, character):
        """Called before a character is puppeted, return False to cancel puppeting."""
        return super().at_pre_puppet(character)
