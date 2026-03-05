# 05 Persistence & Serialization

## 5.1 How Persistence Works

### 5.1.1 The Database
Atheriz uses an SQLite database consisting of a single table for physical object persistence: `objects (id INTEGER, data BLOB)`. Object variables are serialized using `dill` (an enhanced variant of standard Python pickling) and stored directly as blob binaries.

Every persistent entity (Objects, Accounts, Scripts, Channels) exists within this unified table, differentiated purely through class-level property flags (`is_account`, `is_script`, etc.). View [`atheriz/database_setup.py`](../atheriz/database_setup.py) for the schema generation.

### 5.1.2 Save & Load Cycle
The primary interactions pass natively via `atheriz.singletons.objects`:
- `save_objects()` iterates across all loaded objects. Unless globally configured via `ALWAYS_SAVE_ALL`, it exclusively evaluates objects possessing the `is_modified = True` flag, executing a binary write across a structured database transaction.
- `load_objects()` executes a two-pass load architecture. Initially, it deserializes the blobs comprehensively into memory representations. Subsequently, it sequentially executes `resolve_relations()` to translate stored object identifier integers into direct memory pointers.

### 5.1.3 Autosave Settings
Persistence toggles are handled in `settings.py`:
- `AUTOSAVE_PLAYERS_ON_DISCONNECT`
- `AUTOSAVE_ON_SHUTDOWN`
- `AUTOSAVE_ON_RELOAD`
- `ALWAYS_SAVE_ALL` (Enforces bulk serialization regardless of modified state).

Configuring `ALWAYS_SAVE_ALL = True` simplifies development scaling at the explicit cost of I/O performance on widespread production games.

## 5.2 Custom Serialization

### 5.2.1 `__getstate__` and `__setstate__`
Atheriz relies completely on Python's advanced pickling hooks. 
- `__getstate__()` executes during serialization, capturing standard object dictionary values while explicitly stripping properties causing binary execution failures (such as `RLock` configurations and attributes mapped in `_pickle_excludes`).
- `__setstate__(state)` executes uniformly during initialization, reconstructing transient values omitted during execution.

Review `Object.__getstate__` and `Object.__setstate__` inside [`atheriz/objects/base_obj.py`](../atheriz/objects/base_obj.py) for exact logic. 

### 5.2.2 Adding Custom Attributes That Persist
Defining standard Python variables attached directly to `self` guarantees data persistence during standard database checkpoints automatically, provided the target data remains structurally picklable. 

Variables explicitly avoiding serialization are defined inside the `_pickle_excludes` tuple. Common exclusions include unpicklable lambdas, live file pointers, and dynamic HTTP requests.

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
Due to the one-table blob structure, attempting direct Object linkages dynamically inside standard loading sequences crashes consistently. `resolve_relations()` fires iteratively post-load across all instantiated assets to cleanly rebind references utilizing `singletons.objects.get()`. Modifying core relations specifically necessitates extending this exact method.

### 5.2.5 The `DbOps` Mixin
Base interaction SQL occurs within the `DbOps` mixin, granting full replacement access across `example_game/db_ops.py`.
- `get_save_ops()` produces a tuple defining internal `(sql, params)` target logic supporting standard `INSERT OR REPLACE` statements.
- `get_del_ops()` governs standard deletion execution statements.

Overriding these routines permits advanced database integrations involving secondary tables mapped systematically against primary Atheriz IDs.

[Table of Contents](./table_of_contents.md) | [Next: 06 Settings](./06_settings.md)
