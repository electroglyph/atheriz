from typing import Self
from typing import TYPE_CHECKING
from threading import RLock
import time
from atheriz.logger import logger
from atheriz.singletons.get import get_unique_id
from atheriz.singletons.objects import add_object, delete_objects, remove_object
from atheriz.objects.base_flags import Flags
from atheriz.objects.base_db_ops import DbOps
import atheriz.settings as settings
from atheriz.utils import ensure_thread_safe

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


class Script(Flags, DbOps):
    def __init__(self):
        super().__init__()
        self.lock = RLock()
        self.id = -1
        self.name = ""
        self.desc = ""
        self.is_script = True
        self.created_by = -1
        self.child: Object | None = None
        self.date_created = None
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    @classmethod
    def create(
        cls,
        caller: Object | None,
        name: str,
        desc: str = "",
    ) -> Self:
        """
        Create a new object.

        Args:
            session (Session | None): The session to create the object for.
            name (str): The name of the object.
            is_pc (bool, optional): Whether the object is a player character. Defaults to False.
            is_item (bool, optional): Whether the object is an item. Defaults to False.
            is_npc (bool, optional): Whether the object is an NPC. Defaults to False.
            is_mapable (bool, optional): Whether the object is mapable. Defaults to False.
            is_container (bool, optional): Whether the object is a container. Defaults to False.
            is_tickable (bool, optional): Whether the object is tickable. Defaults to False.

        Returns:
            Self: The created object.
        """
        obj = cls()
        obj.id = get_unique_id()
        obj.date_created = time.time()
        obj.created_by = caller.id if caller else -1
        obj.name = name
        obj.desc = desc
        add_object(obj)
        return obj

    def delete(self, caller: Object | None = None, recursive: bool = True):
        if self.child:
            self.remove_hooks()
            if self.id in self.child.scripts:
                self.child.scripts.remove(self.id)
                self.child.is_modified = True

        ops = [self.get_del_ops()]
        delete_objects(ops)
        remove_object(self)
        return True

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            state.pop("lock", None)
            state.pop("child", None)
            return state

    def __setstate__(self, state):
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        object.__setattr__(self, "child", None)

    def at_install(self):
        """
        called when the script is installed on an object
        you can use this event -or- you can hook at_init on the child object
        but you probably don't want to do both
        the main difference is that this code will run right when the script
        is added to the object, and every reboot thereafter.
        if you only do init from 'at_init' then init code will only run after reboot
        """
        pass

    def install_hooks(self, child: Object):
        """
        any functions that start with 'at_' in this class will be considered hooks on the child object
        so at_init on this class will hook at_init on the child object
        you must use one of the decorators above on every hook function in this class.

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
        self.at_install()

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
