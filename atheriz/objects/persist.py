from typing import TYPE_CHECKING, Any, Iterable, List
import atheriz.settings as settings
from pathlib import Path
from atheriz.utils import get_import_path
import json

if TYPE_CHECKING:
    pass


def get_save_path(obj: Any, append_id: bool = True) -> Path:
    return Path(settings.SAVE_PATH) / (get_import_path(obj) + ("." + str(obj.id) if append_id else ""))


def save_iterable(objs: Iterable[Any]) -> None:
    all_objs = []
    save_path: Path | None = None
    for obj in objs:
        if not obj.group_save:
            save_object(obj)
            continue
        if not save_path:
            save_path = get_save_path(obj, False)
        all_objs.append(obj.__getstate__())

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = save_path.with_suffix(save_path.suffix + ".tmp")
        with temp_path.open("w") as f:
            json.dump(all_objs, f)
        temp_path.replace(save_path)


def save_object(obj: Any, filename: str | None = None) -> None:
    if filename:
        path = Path(settings.SAVE_PATH) / filename
    else:
        path = get_save_path(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w") as f:
        json.dump([obj.__getstate__()], f)
    temp_path.replace(path)


def save(obj: Any | List[Any] | set[Any]) -> None:
    if isinstance(obj, (list, set)):
        save_iterable(obj)
    else:
        save_object(obj)
