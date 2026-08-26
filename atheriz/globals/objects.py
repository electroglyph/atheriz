from __future__ import annotations
import time

from atheriz.globals.get import get_id, set_id
import atheriz.globals.get as get_module
from threading import RLock
from atheriz.database_setup import get_database
from atheriz.logger import logger
import atheriz.settings as settings
import dill
import sqlite3
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
class _BoundedDict(dict):
    _limit = 4000

    def __setitem__(self, key, value):
        is_new = key not in self
        super().__setitem__(key, value)
        if is_new and len(self) > self._limit:
            # evict oldest (FIFO)
            oldest = next(iter(self))
            if oldest != key:
                super().__delitem__(oldest)
            else:
                # key was oldest (re-inserted?), remove next oldest
                keys = list(self.keys())
                if len(keys) > 1:
                    super().__delitem__(keys[0])

# not persisted
TEMP_BANNED_IPS: dict[str, float] = _BoundedDict()
TEMP_BANNED_LOCK = RLock()


def is_ip_banned(host: str, now: float | None = None) -> bool:
    if now is None:
        now = time.time()
    with TEMP_BANNED_LOCK:
        expires = TEMP_BANNED_IPS.get(host)
        if expires is None:
            return False
        if now < expires:
            return True
        TEMP_BANNED_IPS.pop(host, None)
        return False


def ban_ip(host: str, expires: float | None = None) -> None:
    if expires is None:
        expires = float("inf")
    with TEMP_BANNED_LOCK:
        TEMP_BANNED_IPS[host] = expires


def unban_ip(host: str) -> None:
    with TEMP_BANNED_LOCK:
        TEMP_BANNED_IPS.pop(host, None)


CREATION_COOLDOWNS: dict[str, float] = _BoundedDict()
CREATION_COOLDOWN_LOCK = RLock()

FAILED_LOGIN_ATTEMPTS: dict[str, int] = _BoundedDict()
FAILED_LOGIN_ATTEMPTS_LOCK = RLock()


def _cooldown_key(host: str) -> str:
    return host


def creation_cooldown_active(op: str, host: str, now: float) -> bool:
    # op is kept for API compat — cooldown is unified per host across all ops
    if host == "?":
        return False
    key = _cooldown_key(host)
    with CREATION_COOLDOWN_LOCK:
        expires = CREATION_COOLDOWNS.get(key)
        if expires is None:
            return False
        if expires > now:
            return True
        CREATION_COOLDOWNS.pop(key, None)
        return False


def apply_creation_cooldown(op: str, host: str, now: float, cooldown: float) -> None:
    if host == "?":
        return
    if cooldown > 0:
        with CREATION_COOLDOWN_LOCK:
            CREATION_COOLDOWNS[_cooldown_key(host)] = now + cooldown


def try_reserve_creation_cooldown(op: str, host: str, now: float, cooldown: float) -> bool:
    if host == "?":
        return True
    key = _cooldown_key(host)
    with CREATION_COOLDOWN_LOCK:
        expires = CREATION_COOLDOWNS.get(key)
        if expires is not None and expires > now:
            return False
        if cooldown > 0:
            CREATION_COOLDOWNS[key] = now + cooldown
        return True


def clear_creation_cooldown(host: str) -> None:
    if host == "?":
        return
    with CREATION_COOLDOWN_LOCK:
        CREATION_COOLDOWNS.pop(_cooldown_key(host), None)

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
    while True:
        with _ALL_OBJECTS_LOCK:
            snapshot = list(_ALL_OBJECTS.values())
        if any(predicate(r) for r in snapshot):
            raise ValueError(error)
        with _ALL_OBJECTS_LOCK:
            current = list(_ALL_OBJECTS.values())
            if current == snapshot:
                add_object(obj)
                return


def remove_object(obj: Object | Channel | Script | Account) -> None:
    """Remove an object from the global object registry."""
    global _ALL_OBJECTS
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS.pop(obj.id, None)


def load_objects():
    """Load objects from the database."""
    global _ALL_OBJECTS
    try:
        db = get_database()
    except RuntimeError:
        logger.warning("load_objects: database closed, skipping")
        return
    objects = {}
    max_id = -1
    rows: list[tuple[int, bytes]] = []
    with db.lock:
        if getattr(db, "_closed", False) is True:
            logger.warning("load_objects: database closed, skipping")
            return
        try:
            cursor = db.connection.cursor()
            cursor.execute("SELECT id, data FROM objects")
            rows = cursor.fetchall()
        except sqlite3.ProgrammingError as e:
            logger.warning(f"load_objects: database closed ({e}), skipping")
            return
    for obj_id, blob in rows:
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
    with get_module._ID_LOCK:
        if max_id > get_module._ID:
            get_module._ID = max_id

    with _ALL_OBJECTS_LOCK:
        snapshot = list(_ALL_OBJECTS.values())
    for obj in snapshot:
        if hasattr(obj, "resolve_relations"):
            obj.resolve_relations()


def _is_still_saveable(obj: Any, *, for_save: bool = False, force: bool = False) -> bool:
    """Return True unless obj has been deleted, made temporary, or removed from the registry.

    Checked at execute time inside the save transaction so a delete racing the
    checkpoint cannot be resurrected by INSERT OR REPLACE.
    When ``for_save`` is True, also checks ``is_modified`` under ``obj.lock``
    so the TOCTOU between an unlocked read and the locked save check cannot
    skip a dirty object.
    """
    try:
        obj_id = object.__getattribute__(obj, "id")
    except AttributeError:
        return False
    with _ALL_OBJECTS_LOCK:
        if _ALL_OBJECTS.get(obj_id) is not obj:
            return False
    with obj.lock:
        if getattr(obj, "is_deleted", False):
            return False
        if getattr(obj, "is_temporary", False):
            return False
        if for_save and not settings.ALWAYS_SAVE_ALL and not force and not getattr(obj, "is_modified", False):
            return False
    return True


def save_objects(force: bool = False):
    """Save modified objects to the database.

    Deleted objects (flagged or already removed from the registry) are skipped,
    both at snapshot time and again immediately before each row is written, so
    a concurrent delete can never be resurrected by a checkpoint.
    """
    try:
        db = get_database()
    except RuntimeError:
        logger.warning("save_objects: database closed, skipping")
        return
    with _ALL_OBJECTS_LOCK:
        snapshot = list(_ALL_OBJECTS.values())
    filtered = []
    for o in snapshot:
        with o.lock:
            if getattr(o, "is_temporary", False) or getattr(o, "is_node", False) or getattr(o, "is_deleted", False):
                continue
        filtered.append(o)
    snapshot = filtered
    pending: list[tuple[Any, tuple[str, tuple]]] = []
    cleared: list[Any] = []
    for obj in snapshot:
        if not _is_still_saveable(obj, for_save=True, force=force):
            continue
        try:
            ops = obj.get_save_ops_clearing()
        except Exception:
            for c in cleared:
                with c.lock:
                    object.__setattr__(c, "is_modified", True)
            raise
        pending.append((obj, ops))
        cleared.append(obj)
    with db.lock:
        if getattr(db, "_closed", False) is True:
            logger.warning("save_objects: database closed, skipping")
            for obj in cleared:
                with obj.lock:
                    object.__setattr__(obj, "is_modified", True)
            return
        try:
            cursor = db.connection.cursor()
            cursor.execute("BEGIN TRANSACTION")
        except sqlite3.ProgrammingError as e:
            logger.warning(f"save_objects: database closed ({e}), skipping")
            for obj in cleared:
                with obj.lock:
                    object.__setattr__(obj, "is_modified", True)
            return
        attempted: list[Any] = []
        try:
            for obj, ops in pending:
                if not _is_still_saveable(obj, for_save=False, force=force):
                    continue
                attempted.append(obj)
                cursor.execute(ops[0], ops[1])
            cursor.execute("COMMIT")
        except Exception:
            try:
                cursor.execute("ROLLBACK")
            except sqlite3.ProgrammingError:
                pass
            for obj in attempted:
                with obj.lock:
                    object.__setattr__(obj, "is_modified", True)
            for obj, _ in pending:
                if obj not in attempted:
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
    try:
        db = get_database()
    except RuntimeError:
        logger.warning("delete_objects: database closed, skipping")
        return
    with db.lock:
        if getattr(db, "_closed", False) is True:
            logger.warning("delete_objects: database closed, skipping")
            return
        try:
            cursor = db.connection.cursor()
            cursor.execute("BEGIN TRANSACTION")
        except sqlite3.ProgrammingError as e:
            logger.warning(f"delete_objects: database closed ({e}), skipping")
            return
        try:
            for op in ops:
                cursor.execute(op[0], op[1])
            cursor.execute("COMMIT")
        except Exception:
            try:
                cursor.execute("ROLLBACK")
            except sqlite3.ProgrammingError:
                pass
            raise
