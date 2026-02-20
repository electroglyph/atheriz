from typing import TYPE_CHECKING
from threading import RLock
import time
import dill
from atheriz.logger import logger

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


def before(func):
    func.is_before = True
    func.is_after = False
    func.is_replace = False
    return func


def after(func):
    func.is_before = False
    func.is_after = True
    func.is_replace = False
    return func


def replace(func):
    func.is_before = False
    func.is_after = False
    func.is_replace = True
    return func


class Script:
    def __init__(self):
        self.lock = RLock()
        self.id = -1
        self.is_pc = False
        self.is_npc = False
        self.is_item = False
        self.is_mapable = False
        self.is_container = False
        self.is_tickable = False
        self.is_account = False
        self.is_channel = False
        self.is_node = False
        self.is_script = True
        self.is_connected = False
        self.created_by = -1
        self.child: Object | None = None

    def install_hooks(self, child: Object):
        """
        any functions that start with 'at_' in this class will be considered hooks on the child object
        so at_init on this class will hook at_init on the child object
        you must use one of the decorators above on every hook function in this class
        before decorator means: run this class' hook code, then run the original child code
        after decorator means: run child code first, then run this class' hook code
        replace decorator means: this class' hook completely replaces the child's code
        """
        self.child = child
        at_funcs = [(d, getattr(self, d)) for d in dir(self) if d.startswith("at_")]
        with child.lock:
            for name, func in at_funcs:
                s = child.hooks.get(name, set())
                s.add(func)
                child.hooks[name] = s
                
    def remove_hooks(self, child: Object | None = None):
        child = self.child if child is None else child
        if child is None:
            logger.error(f"Script has invalid child object, script id: {self.id}")
            return
        at_funcs = [(d, getattr(self, d)) for d in dir(self) if d.startswith("at_")]
        with child.lock:
            for name, func in at_funcs:
                s = child.hooks.get(name, set())
                s.discard(func)
                child.hooks[name] = s
        
        
