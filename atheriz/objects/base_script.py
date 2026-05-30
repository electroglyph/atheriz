from __future__ import annotations
from typing import Self
from typing import TYPE_CHECKING, Callable
from threading import RLock
import time
from atheriz.logger import logger
from atheriz.globals.get import get_unique_id
from atheriz.globals.objects import add_object, delete_objects, remove_object
from atheriz.objects.base_flags import Flags
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
        Create a new persistent Script in the database.

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

    def add_tag(self, tag: str | list[str] | set[str]) -> None:
        """Add one or more tags to this object.

        Args:
            tag (str | list[str] | set[str]): A single tag string, or a list/set of tag strings.
        """
        tags = {tag} if isinstance(tag, str) else set(tag)
        with self.lock:
            self.tags.update(tags)
            self.is_modified = True

    def remove_tag(self, tag: str | list[str] | set[str]) -> None:
        """Remove one or more tags from this object. Missing tags are silently ignored.

        Args:
            tag (str | list[str] | set[str]): A single tag string, or a list/set of tag strings.
        """
        tags = {tag} if isinstance(tag, str) else set(tag)
        with self.lock:
            self.tags.difference_update(tags)
            self.is_modified = True

    def has_tag(self, tag: str | list[str] | set[str], all: bool = False) -> bool:
        """Check whether this object carries the given tags.

        By default, when multiple tags are supplied the check is an ANY match — returns
        ``True`` if at least one of the given tags is present.
        If `all` is set to True, returns ``True`` only if ALL given tags are present.

        Args:
            tag (str | list[str] | set[str]): A single tag string, or a list/set of tag strings.
            all (bool, optional): If True, require all tags to be present. Defaults to False.

        Returns:
            bool: True if the tag conditions are met on this object.
        """
        tags = {tag} if isinstance(tag, str) else set(tag)
        with self.lock:
            if all:
                return tags.issubset(self.tags)
            return bool(tags & self.tags)

    def delete(self, caller: Object | None = None, recursive: bool = True) -> bool:
        """
        Delete this script entirely from the database and remove any active hooks.

        Args:
            caller (Object | None, optional): The object executing the command. Defaults to None.
            recursive (bool, optional): Unused compatibility argument. Defaults to True.

        Returns:
            bool: True upon successful deletion.
        """
        if self.child:
            self.remove_hooks()
            if self.id in self.child.scripts:
                self.child.scripts.remove(self.id)
                self.child.is_modified = True
        if not self.is_temporary:
            ops = [self.get_del_ops()]
            delete_objects(ops)
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
        object.__setattr__(self, "lock", RLock())
        self.__dict__.update(state)
        object.__setattr__(self, "child", None)
        # call __setstate__ for all parent classes
        mro = type(self).mro()
        current_idx = next(
            (
                i
                for i, c in enumerate(mro)
                if c.__module__ == "atheriz.objects.base_script" and c.__qualname__ == "Script"
            ),
            len(mro),
        )
        ancestors = mro[current_idx + 1 :]
        for cls in reversed(ancestors):
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
        self.child = child
        at_funcs = [(d, getattr(self, d)) for d in dir(self) if d.startswith("at_")]
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
        at_funcs = [(d, getattr(self, d)) for d in dir(self) if d.startswith("at_")]
        with child.lock:
            for name, func in at_funcs:
                s = child.hooks.get(name, set())
                s.discard(func)
                child.hooks[name] = s
