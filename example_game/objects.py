# Re-export everything from atheriz.singletons.objects.
# Override or extend functions below to customize behavior.
from atheriz.singletons.objects import (  # noqa: F401
    add_object,
    delete_objects,
    filter_by,
    get,
    load_objects,
    remove_object,
    save_objects,
    TEMP_BANNED_IPS,
)

# def add_object(*args, **kwargs):
#     from atheriz.singletons.objects import add_object as _base_add_object
#     return _base_add_object(*args, **kwargs)

# def delete_objects(ops):
#     from atheriz.singletons.objects import delete_objects as _base_delete_objects
#     return _base_delete_objects(ops)

# def filter_by(l):
#     from atheriz.singletons.objects import filter_by as _base_filter_by
#     return _base_filter_by(l)

# def get(ids):
#     from atheriz.singletons.objects import get as _base_get
#     return _base_get(ids)

# def load_objects():
#     from atheriz.singletons.objects import load_objects as _base_load_objects
#     return _base_load_objects()

# def remove_object(*args, **kwargs):
#     from atheriz.singletons.objects import remove_object as _base_remove_object
#     return _base_remove_object(*args, **kwargs)

# def save_objects(force):
#     from atheriz.singletons.objects import save_objects as _base_save_objects
#     return _base_save_objects(force)

