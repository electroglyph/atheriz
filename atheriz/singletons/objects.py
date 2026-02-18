from atheriz.singletons.get import set_id
from threading import RLock
from atheriz.utils import get_import_path
import atheriz.settings as settings
from pathlib import Path
from atheriz.database_setup import get_database
import dill
from typing import Any, Callable, TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node

_IGNORE_FILES = [
    "salt.txt",
    "server.pid",
    "server.log",
    "areas",
    "transitions",
    "doors",
    "mapdata",
    "spam_accounts.txt",
    "time"
]
# not persisted
TEMP_BANNED_IPS = {}
TEMP_BANNED_LOCK = RLock()

# key = id, value = object
# only access via the lock
_ALL_OBJECTS = {}
_ALL_OBJECTS_LOCK = RLock()

# key = import path, value = set(object ids)
# only access via the lock
_OBJECT_MAP = {}
_OBJECT_MAP_LOCK = RLock()


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


def filter_by_type(import_path: str, l: Callable[[Any], bool]) -> list[Any]:
    """Filter objects by a lambda.

    For example:
    ```python
    filter_by(lambda x: x.is_pc)
    ```

    Args:
        import_path (str): the import path (substring okay) to search for
        l (Callable[[Any], bool]): The lambda to use for filtering.

    Returns:
        list[Any]: The list of objects that match the search criteria.
    """
    results = get_by_type(import_path)
    return [r for r in results if l(r)]


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


def get_by_type(import_path: str) -> list[Any]:
    """Search for objects by type.

    Args:
        import_path (str): The import path of the object to search for.

    Returns:
        list[Any]: The list of objects that match the search criteria.
    """
    if import_path is None:
        return []
    with _ALL_OBJECTS_LOCK:
        s = _OBJECT_MAP.get(import_path)
        if s is None:
            for k in _OBJECT_MAP.keys():
                if import_path.lower() in k.lower():
                    s = _OBJECT_MAP[k]
                    break
            if s is None:
                return []
        return [r for id in s if (r := _ALL_OBJECTS.get(id)) is not None]


def add_object(obj: object) -> None:
    """Add an object to the global object registry."""
    global _ALL_OBJECTS, _OBJECT_MAP
    path = get_import_path(obj)
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS[obj.id] = obj
    with _OBJECT_MAP_LOCK:
        s = _OBJECT_MAP.get(path, set())
        s.add(obj.id)
        _OBJECT_MAP[path] = s


def remove_object(obj: object) -> None:
    """Remove an object from the global object registry."""
    global _ALL_OBJECTS, _OBJECT_MAP
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS.pop(obj.id, None)
    with _OBJECT_MAP_LOCK:
        s = _OBJECT_MAP.get(get_import_path(obj), set())
        s.remove(obj.id)
        _OBJECT_MAP[get_import_path(obj)] = s


# def load_objects():
#     global _ALL_OBJECTS, _OBJECT_MAP
#     with _ALL_OBJECTS_LOCK:
#         _ALL_OBJECTS = dill.load(open(Path(settings.SAVE_PATH) / "objects", "rb"))
#     with _OBJECT_MAP_LOCK:
#         _OBJECT_MAP = dill.load(open(Path(settings.SAVE_PATH) / "object_map", "rb"))
#     with _ALL_OBJECTS_LOCK:
#         biggest_id = max(v.id for v in _ALL_OBJECTS.values() if not v.is_node)
#     set_id(biggest_id)

def load_objects():
    global _ALL_OBJECTS, _OBJECT_MAP
    db = get_database()
    cursor = db.connection.cursor()
    cursor.execute("SELECT id, data FROM objects")
    objects = {}
    object_map = {}
    max_id = -1
    for obj_id, blob in cursor:
        obj = dill.loads(blob)
        objects[obj_id] = obj
        path = get_import_path(obj)
        s = object_map.get(path, set())
        s.add(obj_id)
        object_map[path] = s
        max_id = max(max_id, obj_id)
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS = objects
    with _OBJECT_MAP_LOCK:
        _OBJECT_MAP = object_map
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

# def save_objects():
#     save_path = Path(settings.SAVE_PATH)
#     save_path.mkdir(parents=True, exist_ok=True)

#     with _ALL_OBJECTS_LOCK:
#         objects_snapshot = dict(_ALL_OBJECTS)
#     with _OBJECT_MAP_LOCK:
#         object_map_snapshot = dict(_OBJECT_MAP)

#     def _atomic_save(data, filename):
#         path = save_path / filename
#         temp_path = path.with_suffix(path.suffix + ".tmp")
#         try:
#             with temp_path.open("wb") as f:
#                 dill.dump(data, f)
#             temp_path.replace(path)
#         except Exception as e:
#             from atheriz.logger import logger
#             logger.error(f"Error saving {filename}: {e}")
#             if temp_path.exists():
#                 temp_path.unlink()

#     _atomic_save(objects_snapshot, "objects")
#     _atomic_save(object_map_snapshot, "object_map")