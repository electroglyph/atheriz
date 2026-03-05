# 07 Mixins — Flags, Access, and DbOps

## 7.1 The `Flags` Mixin

### 7.1.1 What Flags Exist
The `Flags` mixin provides uniform boolean properties allowing for immediate identification across game routines. Standard properties include:
`is_pc`, `is_npc`, `is_item`, `is_mapable`, `is_container`, `is_script`, `is_tickable`, `is_account`, `is_channel`, `is_node`, `is_modified`, `is_deleted`, and `is_connected`.

Reference `example_game/flags.py` for standard implementation scaffolding. 

### 7.1.2 Adding Custom Flags
To add new states, append variables safely directly inside the initializer:
```python
object.__setattr__(self, "is_merchant", False)
```
Using `object.__setattr__` avoids executing the customized thread-safe property setter. Modifying the property later inside `Object` methods can use standard assignments reliably.

## 7.2 The `AccessLock` Mixin

### 7.2.1 How Locks Work
The `AccessLock` mixin provides access control for interacting with game objects. It uses a dictionary to store locks, where each lock is a callable that returns True if the interaction is allowed, and False otherwise.
- `add_lock(lock_name, callable)` stores a verification check against a specified label.
- `access(accessing_obj, name)` executes all registered callables, requiring all to return `True` to authorize an interaction.

Example restricting item retrieval exclusively to developers:
```python
obj.add_lock("get", lambda target: getattr(target, 'is_builder', False))
```
Review `example_game/access.py` to examine the standard mixin baseline.

### 7.2.2 Safe vs. Fast Access
Atheriz governs synchronization checking through the `SLOW_LOCKS` configuration override.
- `SLOW_LOCKS = True`: Replaces `access` resolution with `_safe_access`, locking evaluation specifically against localized execution threads safely preventing concurrent modification execution collisions at the direct cost of general logic performance.
- `SLOW_LOCKS = False`: Points the resolution sequence strictly against `_fast_access`, completing validation drastically quicker while exposing data corruption risks across unmanaged real-time modification calls concurrently executing. 

Atheriz forces a native bypass for superusers universally; `access()` yields `True` consistently outside deletion sequences validating `"delete"`.

### 7.2.3 `_pickle_excludes`
The `access` pointer itself is excluded entirely from standard `dill` database pickling protocols natively due to changing dynamically according to `SLOW_LOCKS` configuration execution. Extending the mixin supports modifying the class-level `_pickle_excludes` tuple to prune transient configuration properties effectively.

## 7.3 The `DbOps` Mixin

### 7.3.1 Default Save/Delete Operations
The `DbOps` configuration explicitly defines raw SQL modifications directed against the standard `objects` monolithic block.
- `get_save_ops()` isolates logic generating `INSERT OR REPLACE` string parameters dynamically.
- `get_del_ops()` outlines basic system entity destruction calls.

Reference `example_game/db_ops.py` to target structural data queries directly affecting database executions locally.

### 7.3.2 Customizing Database Operations
Implementing extended configurations requires expanding target lists formatting native relational modifications accurately. If creating secondary tables mapping global strings to standard integer IDs (like usernames), augmenting `get_save_ops()` returning a list handling parallel `SQL` injection arrays permits deep modifications resolving transactionally against atomic operations verified entirely within `delete_objects()`.

[Table of Contents](./table_of_contents.md) | [Next: 08 Input Handling](./08_input_handling.md)
