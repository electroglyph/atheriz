# 07 Mixins: Flags, Access, and DbOps

## 7.1 The `Flags` Mixin

### 7.1.1 What Flags Exist
The `Flags` mixin provides uniform boolean properties allowing for immediate identification across game routines. Standard properties include:
`is_pc`, `is_npc`, `is_item`, `is_mapable`, `is_container`, `is_script`, `is_tickable`, `is_account`, `is_channel`, `is_node`, `is_modified`, `is_deleted`, and `is_connected`.

Reference `example_game/flags.py` for the standard implementation.

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
- `access(accessing_obj, name)`: Executes all registered callables for the lock. If they all return `True`, access is authorized.

Example restricting item retrieval exclusively to builders:
```python
obj.add_lock("get", lambda target: getattr(target, 'is_builder', False))
```
Review `example_game/access.py` to examine the standard mixin baseline.
*Note: Any object where `is_superuser` is `True` automatically bypasses all locks to return `True`, unless the lock name being evaluated is `"delete"`.*

### 7.2.2 Safe vs. Fast Access
Atheriz governs synchronization checking through the `SLOW_LOCKS` configuration toggle in `settings.py`.
- `SLOW_LOCKS = True`: The `access` method resolves as `_safe_access`. This wraps the evaluation in a thread lock to safely prevent concurrent modification collisions. This comes at the cost of general performance.
- `SLOW_LOCKS = False`: The `access` method resolves as `_fast_access`. This completes validation significantly faster but exposes data corruption risks if lock definitions are changing continuously during concurrent executions.

### 7.2.3 `_pickle_excludes`
Because the `access` pointer changes dynamically depending on the `SLOW_LOCKS` configuration, it cannot be safely serialized. It is excluded entirely from standard `dill` database pickling protocols by being included in the class-level `_pickle_excludes` tuple. If your mixins add properties that shouldn't be saved, add them to `_pickle_excludes`.

## 7.3 The `DbOps` Mixin
Modifying `example_game/db_ops.py` allows you to define custom SQL for deletion and save operations. 
- `get_save_ops()` produces a tuple defining internal `(sql, params)` target logic supporting standard `INSERT OR REPLACE` statements.
- `get_del_ops()` governs standard deletion execution statements. By modifying DbOps mixin and creating your own `database_setup.py`, you can use whatever SQL backend with whatever table layout you want.

[Table of Contents](./table_of_contents.md) | [Next: 08 Input Handling](./08_input_handling.md)
