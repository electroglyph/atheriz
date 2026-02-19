from typing import TYPE_CHECKING
from threading import RLock
import time
import dill

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class Script:
    def __init__(self):
        self.lock = RLock()
        self.id = -1
        self.is_pc = False
        self.is_npc = False
        self.is_item = False
        self.is_mapable = False
        self.is_container = False
        self._is_tickable = False
        self.is_account = False
        self.is_channel = False
        self.is_node = False
        self.is_script = True
        self.is_connected = False
        self.created_by = -1

    def at_init(self):
        pass
