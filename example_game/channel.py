from atheriz.objects.base_channel import Channel as BaseChannel
from .flags import Flags
from .db_ops import DbOps
from .access import AccessLock


class Channel(BaseChannel, Flags, DbOps, AccessLock):
    """Custom Channel class. Override methods below to customize behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def at_create(self):
        """Called after a new channel is successfully created."""
        pass

    def at_delete(self, caller=None):
        """Called before the channel is deleted."""
        return super().at_delete(caller)

    def format_message(self, timestamp, sender, message):
        """Format a message. Override in subclasses for custom formatting."""
        return super().format_message(timestamp, sender, message)
