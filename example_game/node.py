from atheriz.objects.nodes import Node as BaseNode
from .flags import Flags
from .db_ops import DbOps
from .access import AccessLock


class Node(BaseNode, Flags, DbOps, AccessLock):
    """Custom Node class. Override methods below to customize behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def at_delete(self, caller):
        """Called before a node is fundamentally deleted from the world grid."""
        return super().at_delete(caller)

    def at_desc(self, looker=None, **kwargs):
        """Called when the node is looked at."""
        pass

    def at_init(self):
        """Called after this node object is deserialized and all its attributes"""
        pass

    def at_object_leave(self, destination, to_exit=None, **kwargs):
        """Called after an object has successfully left the node."""
        pass

    def at_object_receive(self, source, from_exit=None, **kwargs):
        """Called after an object has successfully entered the node."""
        pass

    def at_pre_object_leave(self, destination, to_exit=None, **kwargs):
        """Called before an object leaves the node. Returning False aborts the move."""
        return super().at_pre_object_leave(destination, to_exit, **kwargs)

    def at_pre_object_receive(self, source, from_exit=None, **kwargs):
        """Called before an object enters the node. Returning False aborts the entry."""
        return super().at_pre_object_receive(source, from_exit, **kwargs)

    def at_tick(self):
        """Called every tick."""
        pass
