# 05 Persistence & Serialization

## 5.1 How Persistence Works

### 5.1.1 The Database
Atheriz uses an SQLite database (`save/database.sqlite3`) with 6 tables: `objects (id INTEGER PRIMARY KEY, data BLOB)`, `mapdata`, `areas`, `transitions`, `doors`, `gametime` (`atheriz/database_setup.py:88-99`). Physical game objects (Objects, Accounts, Scripts, Channels) are serialized via `dill` into the `objects` table; map/nodes/time use separate tables/BLOBs (tried WAL `PRAGMA journal_mode=WAL` with fallback to `DELETE`, `database_setup.py:66`). View [`atheriz/database_setup.py`](../atheriz/database_setup.py) for the schema generation.

### 5.1.2 Save & Load Cycle
The primary interactions pass natively via `atheriz.globals.objects` (`atheriz/globals/objects.py:193`):
- `save_objects(force=False)` snapshots under `_ALL_OBJECTS_LOCK`, excludes `is_temporary`/`is_node`/`is_deleted` (`271`), then if `ALWAYS_SAVE_ALL` or `force` saves all else only `is_modified` (`271-278`). Inside a transaction it re-checks `_is_still_saveable()` (`238`) and uses `get_save_ops_clearing()` (`atheriz/objects/base_db_ops.py:23`, atomic clear with restore on exception) per object; rollback re-marks attempted. Guards `db._closed`/`ProgrammingError` (`264-281`).
- `load_objects()` two-pass: try `dill.loads` per row (`200-214`) with `database closed` guard; tracks `max_id` and bumps global `_ID` under `_ID_LOCK` (`223-229`); snapshots under `_ALL_OBJECTS_LOCK`; then `if hasattr(obj, "resolve_relations"): obj.resolve_relations()` (`234`). Relations handle `int`→`get(id)` and `tuple`/`Coord`→`get_node_handler().get_node(loc)` (`atheriz/objects/base_obj.py:484`).

### 5.1.3 Autosave Settings
Persistence toggles are handled in `settings.py`:
- `AUTOSAVE_MINUTES` (`0`=disabled, interval via `AsyncTicker` `atheriz/globals/autosave.py:52`) — saves `objects` + `MapHandler` + `NodeHandler` + `GameTime` and notifies `server` channel (`autosave.py:22-49`)
- `AUTOSAVE_PLAYERS_ON_DISCONNECT`
- `AUTOSAVE_ON_SHUTDOWN` / `AUTOSAVE_ON_RELOAD` (also gate map/node saves, `atheriz/globals/startstop.py:67,144`)
- `ALWAYS_SAVE_ALL` (Always save all the things, even when they haven't changed; bypassed via `force` param)

### 5.1.4 Trust Model

`save/` (`database.sqlite3`, `-wal`, `-shm`, and `mapdata`/`areas`/`transitions`/`doors`/`gametime` BLOBs inside the same database) and `secret/` (`salt.txt`, `admin.token`) are **fully trusted**. Anyone who can write them can execute arbitrary code as the server user on the next `load_objects()` / `MapHandler.__init__` / `NodeHandler.load()` / `GameTime.load()` via `dill.loads` — `dill` serializes code objects and classes by design and has no safe subset. Run the server under a dedicated OS user, `chmod 700 save secret` (and `600` for files inside), do not expose these directories through backups, shared hosting, or HTTP APIs, and treat them like credentials. `atheriz/web` never reads or writes blobs or the database; the engine must never expose `dill` blobs or raw DB rows through network protocols, web endpoints, or player-reachable commands. Revisit this section if any blob import or upload feature is added.

## 5.2 Custom Serialization

### 5.2.1 `__getstate__` and `__setstate__`
Atheriz relies completely on Python's advanced pickling hooks.
- `__getstate__()` (`atheriz/objects/base_obj.py:399`) copies `__dict__`, pops MRO `_pickle_excludes`, pops `session/lock/hooks`, converts `location`/`home` `Node`→`Coord` and `Object`→`id`, coerces `privilege_level` to `int`, reverts `_puppet_restore` keys.
- `__setstate__(state)` (`459`) recreates `RLock`, restores `Privilege` IntEnum, resets `session/group_channel/hooks`, restores ancestor `__setstate__`, coerces legacy `list` `_contents`→`set`, calls `ensure_thread_safe` if enabled. `resolve_relations` (`484`) then calls `at_init()` (`514`), so `at_init` runs post-deserialization; `__init__` must be no-arg compatible for reloader (`atheriz/reloader.py:264`).

Review `Object.__getstate__` and `Object.__setstate__` inside [`atheriz/objects/base_obj.py`](../atheriz/objects/base_obj.py) for exact logic. `AccessLock._pickle_excludes = ("access",)` (`atheriz/objects/base_lock.py:12`) and `__setstate__` rebinds `access` to `_safe/_fast` per current `SLOW_LOCKS`. 

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
Two passes are needed because when an object references another ID, that ID might not be loaded into memory yet. `resolve_relations()` fires iteratively post-load across all instantiated objects to rebind references to other objects. Guarded by `if hasattr(obj, "resolve_relations"): obj.resolve_relations()` (`atheriz/globals/objects.py:234`), so an empty method is unnecessary.

### 5.2.5 The `DbOps` Mixin
Modifying `db_ops.py` in your game folder (generated from `atheriz/objects/base_db_ops.py`) allows custom SQL. `atheriz/objects/base_db_ops.py` defines:
- `get_save_ops()` → `(sql, params)` `INSERT OR REPLACE`; `get_save_ops_clearing()` (`23`) atomically clears `is_modified` with restore on exception (used live by `save_objects:295`, contract: only `self.lock`, no foreign locks to avoid AB-BA with `move_to`)
- `get_del_ops()` → `DELETE FROM objects WHERE id = ?` (`46`). By modifying DbOps and `database_setup.py`, you can use any backend/table layout.

[Table of Contents](./table_of_contents.md) | [Next: 06 Settings](./06_settings.md)
