# 07 Mixins: Flags, Access, and DbOps

## 7.1 The `Flags` Mixin

### 7.1.1 What Flags Exist
The `Flags` mixin provides uniform boolean properties allowing for immediate identification across game routines. Standard properties `atheriz/objects/base_flags.py:5` include:
`is_pc`, `is_npc`, `is_item`, `is_mapable`, `is_container`, `is_script`, `is_tickable` (stored as `_is_tickable`), `is_account`, `is_channel`, `is_node`, `is_modified`, `is_deleted`, `is_connected`, plus `is_temporary` (`False`, `save_objects` skips), `is_banned`, `can_hear`, and `tags: set[str]` with helpers `add_tag/remove_tag/has_tag` (`base_flags.py:29`). `Object` property `is_tickable` (`atheriz/objects/base_obj.py:529`) also registers with the async ticker.

Reference the `flags.py` in your game folder (generated from `atheriz/objects/base_flags.py`) for the standard implementation.

### 7.1.2 Adding Custom Flags
To add new states (like custom flags), set the attribute directly in the `Flags` initializer:
```python
object.__setattr__(self, "is_merchant", False)
```
Using `object.__setattr__` bypasses the customized thread-safe property setter during initialization. When modifying the property later inside `Object` methods, you can use normal standard assignments (e.g., `self.is_merchant = True`).

## 7.2 The `AccessLock` Mixin

### 7.2.1 How Locks Work
The `AccessLock` mixin provides access control for interacting with game objects. It uses a dictionary to store locks, where each lock is a list of callables. When the lock is checked, every callable must return `True` for the interaction to be allowed.

- `add_lock(lock_name, callable)`: Stores a verification check against a specified lock name.
- `clear_locks_by_name(lock_name)` (`atheriz/objects/base_lock.py:40`): wipes a lock entry.
- `access(accessing_obj, name)`: Executes all registered callables for the lock. If they all return `True`, access is authorized.

Example restricting item retrieval exclusively to builders:
```python
obj.add_lock("get", lambda target: getattr(target, 'is_builder', False))
```
Review the `access.py` in your game folder (generated from `atheriz/objects/base_lock.py`) to examine the standard mixin baseline.
*Note: Self-`get` and self-`delete` are always denied even for superusers (`if id==self.id and name in ["delete","get"]: return False` before `is_superuser` check, `atheriz/objects/base_lock.py:52`). A superuser bypasses all *other* objects' locks (including `delete` on others).*

### 7.2.2 Safe vs. Fast Access
Atheriz governs synchronization checking through the `SLOW_LOCKS` configuration toggle in `settings.py` (`atheriz/settings.py:133`).
- `SLOW_LOCKS = True`: `access` → `_safe_access` inside `with self.lock:` (`atheriz/objects/base_lock.py:50`).
- `SLOW_LOCKS = False`: `access` → `_fast_access` without lock — faster but `locks` dict may tear.

Under free-threaded Python (`sys._is_gil_enabled()==False`) the engine forces `SLOW_LOCKS=True` (`settings.py:143`), so fast mode is unavailable on 3.14t.

### 7.2.3 `_pickle_excludes`
Because `access` is rebased per `SLOW_LOCKS`, it is excluded via `_pickle_excludes = ("access",)` (`atheriz/objects/base_lock.py:12`); `__setstate__` rebinds `access` to `_safe/_fast` per current setting (`74`). MRO loop in `atheriz/objects/base_obj.py:401` pops per-class excludes; add custom non-picklable attrs to your class's `_pickle_excludes`.

## 7.3 The `DbOps` Mixin
Modifying `db_ops.py` in your game folder (generated from `atheriz/objects/base_db_ops.py`) allows custom SQL. As in §5.2.5, `atheriz/objects/base_db_ops.py` defines `get_save_ops()`, `get_save_ops_clearing()` (atomic `is_modified` clear, used live by `save_objects`), and `get_del_ops()` (`DELETE…`). By modifying DbOps and `database_setup.py`, you can use any backend/table layout.

[Table of Contents](./table_of_contents.md) | [Next: 08 Input Handling](./08_input_handling.md)
