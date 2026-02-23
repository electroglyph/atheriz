import atheriz.settings as settings
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
        if settings.SLOW_LOCKS:
            self.access = self._safe_access
        else:
            self.access = self._fast_access

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

    def _safe_access(self, accessing_obj: Object, name: str):
        if accessing_obj.is_superuser and name != "delete":
            return True
        with self.lock:
            lock_list = self.locks.get(name, [])
            for lock in lock_list:
                if not lock(accessing_obj):
                    return False
            return True

    def _fast_access(self, accessing_obj: Object, name: str):
        if accessing_obj.is_superuser and name != "delete":
            return True
        lock_list = self.locks.get(name, [])
        for lock in lock_list:
            if not lock(accessing_obj):
                return False
        return True
    
    def __setstate__(self, state):
        if not hasattr(self, "locks"):
            object.__setattr__(self, "locks", state.get("locks", {}))
        if settings.SLOW_LOCKS:
            object.__setattr__(self, "access", self._safe_access)
        else:
            object.__setattr__(self, "access", self._fast_access)