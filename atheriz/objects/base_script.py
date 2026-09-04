from __future__ import annotations
from typing import Self
from typing import TYPE_CHECKING, Callable
from threading import RLock
import time
from atheriz.logger import logger
from atheriz.globals.get import get_unique_id
from atheriz.globals.objects import add_object, delete_objects, remove_object
from atheriz.objects.base_flags import Flags, FLAG_DEFAULTS
from atheriz.objects.base_db_ops import DbOps
import atheriz.settings as settings
from atheriz.utils import ensure_thread_safe

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


def before(func: Callable) -> Callable:
    """
    Decorator designating a script hook to execute BEFORE the child object's native method.

    Args:
        func (Callable): The method being decorated.

    Returns:
        Callable: The flagged method.
    """
    func.is_before = True
    func.is_after = False
    func.is_replace = False
    return func


def after(func: Callable) -> Callable:
    """
    Decorator designating a script hook to execute AFTER the child object's native method.

    Args:
        func (Callable): The method being decorated.

    Returns:
        Callable: The flagged method.
    """
    func.is_before = False
    func.is_after = True
    func.is_replace = False
    return func


def replace(func: Callable) -> Callable:
    """
    Decorator designating a script hook to completely REPLACE the child object's native method.

    Args:
        func (Callable): The method being decorated.

    Returns:
        Callable: The flagged method.
    """
    func.is_before = False
    func.is_after = False
    func.is_replace = True
    return func


class Script(Flags, DbOps):
    def __init__(self):
        self.lock = RLock()
        super().__init__()
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
        Create a new Script in memory. It is not written to the database here;
        it is marked as modified and persisted at the next save checkpoint
        unless `is_temporary` is set.

        Args:
            caller (Object | None): The object executing the creation.
            name (str): The name of the script.
            desc (str, optional): A description for the script. Defaults to "".

        Returns:
            Self: The generated Script object.
        """
        obj = cls()
        obj.id = get_unique_id()
        obj.date_created = time.time()
        obj.created_by = caller.id if caller else -1
        obj.name = name
        obj.desc = desc
        add_object(obj)
        return obj

    def delete(self, caller: Object | None = None, recursive: bool = True) -> bool:
        """
        Delete this script entirely from the database and remove any active hooks.

        Args:
            caller (Object | None, optional): The object executing the command. Defaults to None.
            recursive (bool, optional): Unused compatibility argument. Defaults to True.

        Returns:
            bool: True upon successful deletion.
        """
        ops = [self.get_del_ops()] if not getattr(self, "is_temporary", False) else []
        if ops:
            delete_objects(ops)
        with self.lock:
            self.is_deleted = True
        child = self.child
        if child is not None:
            self.remove_hooks(child)
            with child.lock:
                if self.id in child.scripts:
                    child.scripts.remove(self.id)
                    child.is_modified = True
            object.__setattr__(self, "child", None)
        remove_object(self)
        return True

    def __getstate__(self):
        with self.lock:
            state = self.__dict__.copy()
            for cls in type(self).mro():
                # remove excluded keys
                excludes = getattr(cls, "_pickle_excludes", ())
                for key in excludes:
                    state.pop(key, None)
            state.pop("lock", None)
            state.pop("child", None)
            return state

    def __setstate__(self, state):
        current_child = getattr(self, "child", None)
        object.__setattr__(self, "lock", RLock())
        # Raw dict access: bulk restore must not trip the write-through
        # __dict__ view (no per-key dirty-marking on the load path).
        object.__getattribute__(self, "__dict__").update(state)
        # Preserve the live link during in-place hot reload; fresh deserialized
        # scripts still start without a child and are linked during resolution.
        object.__setattr__(self, "child", current_child)
        for _name, _default in FLAG_DEFAULTS.items():
            if _name not in self.__dict__:
                object.__setattr__(self, _name, _default() if _name == "tags" else _default)
        mro = type(self).mro()
        try:
            cur = mro.index(__class__)
        except ValueError:
            cur = -1
        for cls in reversed(mro[cur + 1 :]):
            if "__setstate__" in cls.__dict__:
                cls.__setstate__(self, state)
        if settings.THREADSAFE_GETTERS_SETTERS:
            ensure_thread_safe(self)

    def at_install(self) -> None:
        """
        Called when the script is assigned to and installed on an object.

        This occurs immediately when the script is attached, and upon every subsequent
        server reboot. You can use this for initialization code, or alternatively hook
        `at_init` on the child. `at_init` will only run on object instantiation (server boot/creation).
        """
        pass

    def install_hooks(self, child: Object | Node) -> None:
        """
        Attaches all properly-decorated `at_*` hook methods in this script to a child object.

        Every hook in this class must be prefixed with `at_` to mirror the child object's method,
        and decorated with `@before`, `@after`, or `@replace`.

        Args:
            child (Object | Node): The target object experiencing the method injection.
        """
        with self.lock:
            if self.child is not None and self.child is not child:
                raise ValueError(f"Script {self.id} already attached to {self.child} cannot be attached to {child}")
            self.child = child
        at_funcs = [
            (d, getattr(self, d))
            for d in dir(self)
            if d.startswith("at_")
            and (
                getattr(getattr(self, d), "is_before", False)
                or getattr(getattr(self, d), "is_after", False)
                or getattr(getattr(self, d), "is_replace", False)
            )
        ]
        with child.lock:
            for name, func in at_funcs:
                s = child.hooks.get(name, set())
                s.add(func)
                child.hooks[name] = s
        self.at_install()

    def remove_hooks(self, child: Object | Node | None = None) -> None:
        """
        Detaches all hook methods in this Script from the currently-assigned child object.

        Args:
            child (Object | Node | None, optional): An explicitly provided object to detach from.
            Defaults to the currently active child payload.
        """
        child = self.child if child is None else child
        if child is None:
            logger.error(f"Script has invalid child object, script id: {self.id}")
            return
        at_funcs = [
            (d, getattr(self, d))
            for d in dir(self)
            if d.startswith("at_")
            and (
                getattr(getattr(self, d), "is_before", False)
                or getattr(getattr(self, d), "is_after", False)
                or getattr(getattr(self, d), "is_replace", False)
            )
        ]
        with child.lock:
            for name, func in at_funcs:
                s = child.hooks.get(name, set())
                s.discard(func)
                s.difference_update(
                    [hook for hook in s if getattr(hook, "__self__", None) is self]
                )
                child.hooks[name] = s
