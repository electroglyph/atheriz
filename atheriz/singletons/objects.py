from atheriz.singletons.get import set_id
from atheriz.objects.persist import save
from threading import Lock, RLock
from atheriz.utils import get_import_path, instance_from_string
import atheriz.settings as settings
from pathlib import Path
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


def load_files() -> Any:
    """
    Load all objects from the save directory.
    """
    biggest_id = -1

    # Clean up any leftover temp files from crashed saves
    tmp_files = list(Path(settings.SAVE_PATH).glob("*.tmp"))
    for tmp_file in tmp_files:
        print(f"Cleaning up stale temp file: {tmp_file.name}")
        tmp_file.unlink()

    for file in Path(settings.SAVE_PATH).iterdir():
        if file.name in _IGNORE_FILES:
            continue
        if file.is_file() and not file.name.endswith(".tmp"):
            with file.open("r") as f:
                d = json.load(f)
            for x in d:
                if x.get("is_deleted", False):
                    continue
                obj = instance_from_string(x["__import_path__"])
                obj.__setstate__(x)
                add_object(obj)
                if obj.id > biggest_id:
                    biggest_id = obj.id
    set_id(biggest_id)


# def save_objects():
#     with _ALL_OBJECTS_LOCK:
#         objs = list(_ALL_OBJECTS.values())
#     save(objs)

def load_objects():
    global _ALL_OBJECTS, _OBJECT_MAP
    with _ALL_OBJECTS_LOCK:
        _ALL_OBJECTS = dill.load(open(Path(settings.SAVE_PATH) / "objects", "rb"))
    with _OBJECT_MAP_LOCK:
        _OBJECT_MAP = dill.load(open(Path(settings.SAVE_PATH) / "object_map", "rb"))

def save_objects():
    save_path = Path(settings.SAVE_PATH)
    save_path.mkdir(parents=True, exist_ok=True)

    def _atomic_save(data, filename, lock):
        path = save_path / filename
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with lock:
            try:
                with temp_path.open("wb") as f:
                    dill.dump(data, f)
                temp_path.replace(path)
            except Exception as e:
                from atheriz.logger import logger
                logger.error(f"Error saving {filename}: {e}")
                if temp_path.exists():
                    temp_path.unlink()

    _atomic_save(_ALL_OBJECTS, "objects", _ALL_OBJECTS_LOCK)
    _atomic_save(_OBJECT_MAP, "object_map", _OBJECT_MAP_LOCK)