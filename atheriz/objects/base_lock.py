from __future__ import annotations
from typing import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class AccessLock:
    # fields to exclude from pickle
    _pickle_excludes = ("access",)

    def __init__(self):
        # dict[str, list[Callable]] = {}
        object.__setattr__(self, "locks", {})

    def add_lock(self, lock_name: str, callable: Callable):
        """
        Add a lock to this object.

        For example:
        ```python
        obj.add_lock("get", lambda x: x.is_builder)
        ```

        Args:
            lock_name (str): The name of the lock to add.
            callable (Callable): The callable to add to the lock.
        """
        with self.lock:
            l = self.locks.get(lock_name, [])
            l.append(callable)
            self.locks[lock_name] = l

    def clear_locks_by_name(self, lock_name: str):
        """
        Clear all locks by name.

        Args:
            lock_name (str): The name of the lock to clear.
        """
        with self.lock:
            self.locks.pop(lock_name, None)

    def access(self, accessing_obj: Object, name: str):
        # workaround for doors
        if getattr(self, "id", None) is not None and getattr(accessing_obj, "id", None) == self.id and name in ["delete", "get"]:
            return False
        if getattr(accessing_obj, "is_superuser", False):
            return True
        with self.lock:
            lock_list = self.locks.get(name, [])
            for lock in lock_list:
                if not lock(accessing_obj):
                    return False
            return True

    def __setstate__(self, state):
        if not hasattr(self, "locks"):
            object.__setattr__(self, "locks", state.get("locks", {}))
