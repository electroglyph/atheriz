from __future__ import annotations
from atheriz.globals.get import set_id
from threading import RLock
from atheriz.database_setup import get_database
from atheriz.logger import logger
import atheriz.settings as settings
import dill
from typing import Any, Callable, TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_channel import Channel
    from atheriz.objects.base_script import Script
    from atheriz.objects.base_account import Account

_IGNORE_FILES = [
    "salt.txt",
    "server.pid",
    "server.log",
    "areas",
    "transitions",
    "doors",
    "mapdata",
    "spam_accounts.txt",
    "time",
]
# not persisted
TEMP_BANNED_IPS = {}
TEMP_BANNED_LOCK = RLock()
CREATION_COOLDOWNS = {}
CREATION_COOLDOWN_LOCK = RLock()


def creation_cooldown_active(op: str, host: str, now: float) -> bool:
    """Return True if ``op`` for ``host`` is still within its cooldown window."""
    key = f"{op}:{host}"
    with CREATION_COOLDOWN_LOCK:
        expires = CREATION_COOLDOWNS.get(key)
        if expires is None:
            return False
        if expires > now:
            return True
        CREATION_COOLDOWNS.pop(key, None)
        return False


def apply_creation_cooldown(op: str, host: str, now: float, cooldown: float) -> None:
    """Record a creation cooldown expiry for ``op`` and ``host``."""
    if cooldown > 0:
        with CREATION_COOLDOWN_LOCK:
            CREATION_COOLDOWNS[f"{op}:{host}"] = now + cooldown


def try_reserve_creation_cooldown(op: str, host: str, now: float, cooldown: float) -> bool:
    key = f"{op}:{host}"
    with CREATION_COOLDOWN_LOCK:
        expires = CREATION_COOLDOWNS.get(key)
        if expires is not None and expires > now:
            return False
        if cooldown > 0:
            CREATION_COOLDOWNS[key] = now + cooldown
        return True

# key = id, value = object
# only access via the lock
_ALL_OBJECTS = {}
_ALL_OBJECTS_LOCK = RLock()


def filter_by(l: Callable[[Any], bool]) -> list[Any]:
    """Filter objects by a lambda.

    For example:
    ```python
    filter_by(lambda x: x.is_pc)
    ```

    Args:
        l (Callable[[Any], bool]): The lambda to use for filtering.

    Returns:
        list[Any]: The list of objects that match the search criteria.
    """
    with _ALL_OBJECTS_LOCK:
        snapshot = list(_ALL_OBJECTS.values())
    return [r for r in snapshot if l(r)]


def get_by_tag(tag: str | list[str] | set[str], all: bool = False) -> list[Any]:
    """Search for objects by tag.

    By default, matches objects that have ANY of the given tags.
    If `all` is True, returns only objects that have ALL of the given tags.

    Args:
        tag (str | list[str] | set[str]): A single tag or list/set of tags to search for.
        all (bool, optional): If True, require all tags to be present. Defaults to False.

    Returns:
        list[Any]: The list of objects that match the tag criteria.
    """
    tags = {tag} if isinstance(tag, str) else set(tag)
    if all:
        return filter_by(lambda x: tags.issubset(getattr(x, "tags", set())))
    return filter_by(lambda x: bool(tags & getattr(x, "tags", set())))


def get(ids: int | Iterable[int]) -> list[Any]:
    """Search for objects by ID.

    Args:
        ids (int | list[int]): The ID or list of IDs to search for.

    Returns:
        list[object]: The list of objects that match the search criteria.
    """
    with _ALL_OBJECTS_LOCK:
        if ids is None:
            return []
        if isinstance(ids, int):
            r = _ALL_OBJECTS.get(ids)
            return [r] if r is not None else []
        return [r for id in ids if (r := _ALL_OBJECTS.get(id)) is not None]


def add_object(obj: Object | Channel | Script | Account) -> None:
    """Add an object to the global object registry."""
    global _ALL_OBJECTS
    with _ALL_OBJECTS_LOCK:
        stale_keys = [k for k, v in _ALL_OBJECTS.items() if v is obj and k != obj.id]
        for k in stale_keys:
            _ALL_OBJECTS.pop(k, None)
        _ALL_OBJECTS[obj.id] = obj


def add_object_unique(
    obj: Object | Channel | Script | Account,
    predicate: Callable[[Any], bool],
    error: str,
) -> None:
    """Register ``obj`` only if no registered object satisfies ``predicate``.

    The uniqueness check and the insert share one critical section, so racing
    creators cannot both pass the check.

    Raises:
        ValueError: If an already-registered object satisfies ``predicate``.
    """
    with _ALL_OBJECTS_LOCK:
        if any(predicate(r) for r in _ALL_OBJECTS.values()):
            raise ValueError(error)
        add_object(obj)


def remove_object(obj: Object | Channel | Script | Account) -> None:
    """Remove an object from the global object registry."""
    global _ALL_OBJECTS
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS.pop(obj.id, None)


def load_objects():
    """Load objects from the database."""
    global _ALL_OBJECTS
    db = get_database()
    objects = {}
    max_id = -1
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("SELECT id, data FROM objects")
        for obj_id, blob in cursor:
            try:
                obj = dill.loads(blob)
            except Exception as e:
                logger.error(f"Error loading object {obj_id}: {e}")
                continue
            objects[obj_id] = obj
            max_id = max(max_id, obj_id)
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS.clear()
        _ALL_OBJECTS.update(objects)
        set_id(max_id)

    with _ALL_OBJECTS_LOCK:
        snapshot = list(_ALL_OBJECTS.values())
    for obj in snapshot:
        if hasattr(obj, "resolve_relations"):
            obj.resolve_relations()


def _is_still_saveable(obj: Any) -> bool:
    """Return True unless obj has been deleted or removed from the registry.

    Checked at execute time inside the save transaction so a delete racing the
    checkpoint cannot be resurrected by INSERT OR REPLACE.
    """
    with obj.lock:
        if getattr(obj, "is_deleted", False):
            return False
        obj_id = obj.id
    with _ALL_OBJECTS_LOCK:
        return _ALL_OBJECTS.get(obj_id) is obj


def save_objects(force: bool = False):
    """Save modified objects to the database.

    Deleted objects (flagged or already removed from the registry) are skipped,
    both at snapshot time and again immediately before each row is written, so
    a concurrent delete can never be resurrected by a checkpoint.
    """
    db = get_database()
    with _ALL_OBJECTS_LOCK:
        snapshot = list(
            o
            for o in _ALL_OBJECTS.values()
            if not getattr(o, "is_temporary", False)
            and not getattr(o, "is_node", False)
            and not getattr(o, "is_deleted", False)
        )
    to_save = snapshot if settings.ALWAYS_SAVE_ALL or force else [s for s in snapshot if getattr(s, "is_modified", False)]
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("BEGIN TRANSACTION")
        attempted = []
        try:
            for obj in to_save:
                if not _is_still_saveable(obj):
                    continue
                attempted.append(obj)
                ops = obj.get_save_ops_clearing()
                cursor.execute(ops[0], ops[1])
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            for obj in attempted:
                with obj.lock:
                    object.__setattr__(obj, "is_modified", True)
            raise


def delete_objects(ops: list[tuple[str, tuple]]):
    """Delete objects using a list of SQL operations in a transaction.

    Args:
        ops (list[tuple[str, tuple]]): The list of SQL operations to execute.
    """
    if not ops:
        return
    db = get_database()
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            for op in ops:
                cursor.execute(op[0], op[1])
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise
