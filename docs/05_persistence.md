# 05 Persistence & Serialization

## 5.1 How Persistence Works

### 5.1.1 The Database
Atheriz uses an SQLite database consisting of a single table for physical object persistence: `objects (id INTEGER, data BLOB)`. Object variables are serialized using `dill` (an enhanced variant of standard Python pickling) and stored directly as blob binaries.

Every persistent entity (Objects, Accounts, Scripts, Channels) exists within this unified table, differentiated by unique IDs and class-level property flags (`is_account`, `is_script`, etc.). View [`atheriz/database_setup.py`](../atheriz/database_setup.py) for the schema generation.

### 5.1.2 Save & Load Cycle
The primary interactions pass natively via `atheriz.singletons.objects`:
- `save_objects()` iterates across all loaded objects. Unless globally configured via `ALWAYS_SAVE_ALL`, it exclusively evaluates objects possessing the `is_modified = True` flag, executing a write with a structured database transaction.
- `load_objects()` executes a two-pass load architecture. Initially, it deserializes the blobs into memory. After deserialization, it sequentially executes `resolve_relations()` to translate stored object identifier integers into their cached objects.

### 5.1.3 Autosave Settings
Persistence toggles are handled in `settings.py`:
- `AUTOSAVE_PLAYERS_ON_DISCONNECT`
- `AUTOSAVE_ON_SHUTDOWN`
- `AUTOSAVE_ON_RELOAD`
- `ALWAYS_SAVE_ALL` (Always save all the things, even when they haven't changed)

## 5.2 Custom Serialization

### 5.2.1 `__getstate__` and `__setstate__`
Atheriz relies completely on Python's advanced pickling hooks. 
- `__getstate__()` executes during serialization, capturing standard object dictionary values while explicitly stripping properties causing binary execution failures (such as `RLock` configurations and attributes mapped in `_pickle_excludes`).
- `__setstate__(state)` executes during initialization, reconstructing transient values omitted during execution.
__setstate__ sort of replaces __init__, initialization should be done in __setstate__. Also, custom classes with __init__ defined should not require arguments in order to remain compatible with deserialization.
__setstate__ also calls the at_init() hook.

Review `Object.__getstate__` and `Object.__setstate__` inside [`atheriz/objects/base_obj.py`](../atheriz/objects/base_obj.py) for exact logic. 

### 5.2.2 Adding Custom Attributes That Persist
Defining standard Python variables attached directly to `self` guarantees data persistence during standard database checkpoints automatically, provided the target data remains picklable. 

Variables explicitly avoiding serialization are defined inside the `_pickle_excludes` tuple. Things to avoid pickling include Thread objects and other OS primitives.

### 5.2.3 Adding Custom Attributes That Don't Persist
To manage transient system objects (like an active timer pool):

```python
class MyObject(Object):
    _pickle_excludes = ("_active_timers",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_timers = {}

    def __setstate__(self, state):
        super().__setstate__(state)
        # Re-initialize the transient variable during database restore
        self._active_timers = {}
```

### 5.2.4 The `resolve_relations` Pass
Two passes are needed because when an object references another ID, that ID might not be loaded into memory yet. `resolve_relations()` fires iteratively post-load across all instantiated objects to rebind references to other objects. If a custom class doesn't need this functionality, it should still have an empty `resolve_relations` method.

### 5.2.5 The `DbOps` Mixin
Modifying `example_game/db_ops.py` allows you to define custom SQL for deletion and save operations. 
- `get_save_ops()` produces a tuple defining internal `(sql, params)` target logic supporting standard `INSERT OR REPLACE` statements.
- `get_del_ops()` governs standard deletion execution statements. By modifying DbOps mixin and creating your own `database_setup.py`, you can use whatever SQL backend with whatever table layout you want.

[Table of Contents](./table_of_contents.md) | [Next: 06 Settings](./06_settings.md)
