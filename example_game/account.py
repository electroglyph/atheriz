from atheriz.objects.base_account import Account as BaseAccount
from .flags import Flags
from .db_ops import DbOps


class Account(BaseAccount, Flags, DbOps):
    """Custom Account class. Override methods below to customize behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def at_create(self):
        """Called after a new account is successfully created."""
        pass

    def at_delete(self, caller=None):
        """Called before the account is deleted."""
        return super().at_delete(caller)

    def at_disconnect(self):
        """Called when a session associated with this account disconnects."""
        pass

    def at_pre_puppet(self, character):
        """Called before a character is puppeted by this account."""
        return super().at_pre_puppet(character)
