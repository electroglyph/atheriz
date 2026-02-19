from atheriz.singletons.get import set_id
from threading import RLock
from atheriz.utils import get_import_path
from atheriz.database_setup import get_database
import dill
from typing import Any, Callable, TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

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
        return [r for id in _ALL_OBJECTS.keys() if (r := _ALL_OBJECTS.get(id)) is not None and l(r)]


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


def add_object(obj: Object) -> None:
    """Add an object to the global object registry."""
    global _ALL_OBJECTS
    path = get_import_path(obj)
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS[obj.id] = obj


def remove_object(obj: Object) -> None:
    """Remove an object from the global object registry."""
    global _ALL_OBJECTS
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS.pop(obj.id, None)


def load_objects():
    global _ALL_OBJECTS
    db = get_database()
    objects = {}
    max_id = -1
    with db.lock:
        cursor = db.connection.cursor()
        cursor.execute("SELECT id, data FROM objects")
        for obj_id, blob in cursor:
            obj = dill.loads(blob)
            objects[obj_id] = obj
            max_id = max(max_id, obj_id)
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS = objects
    set_id(max_id)


def save_objects():
    db = get_database()
    cursor = db.connection.cursor()
    with _ALL_OBJECTS_LOCK:
        snapshot = list(_ALL_OBJECTS.values())
    to_save = [s for s in snapshot if s.is_modified]
    with db.lock:
        cursor.execute("BEGIN TRANSACTION")
        for obj in to_save:
            ops = obj.get_save_ops()
            cursor.execute(ops[0], ops[1])
            obj.is_modified = False
        cursor.execute("COMMIT")


def delete_objects(ops: list[tuple[str, tuple]]):
    """
    Execute a list of SQL operations in a transaction.
    """
    if not ops:
        return
    db = get_database()
    cursor = db.connection.cursor()
    with db.lock:
        cursor.execute("BEGIN TRANSACTION")
        for op in ops:
            cursor.execute(op[0], op[1])
        cursor.execute("COMMIT")
