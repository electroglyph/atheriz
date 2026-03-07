# 02 Core Concepts

## 2.1 Objects (`Object`)

### 2.1.1 What is an Object?
An `Object` is the universal entity within Atheriz. Anything that is not a static room—including players, NPCs, items, and containers—is represented by an `Object` or a subclass thereof. Important attributes include `id`, `name`, `desc`, and `location`. Classification flags such as `is_pc`, `is_npc`, `is_item`, `is_container`, and `is_mapable` determine the object's identity and interaction rules. These flags are inherited via the `Flags` mixin.

For exact attribute definitions, refer to [`atheriz/objects/base_obj.py`](../atheriz/objects/base_obj.py).

### 2.1.2 Creating Objects
Objects are generated via the `Object.create()` class method. This method allocates the object's ID, registers it with the global cache, and calls the `at_create` hook for customized setup. Note: objects are not persisted to the database until `Object.save()` is called.

Key parameters include `session`, `name`, `desc`, `location`, `is_item`, `is_npc`, `is_mapable`, `is_container`, `is_tickable`, and `tick_seconds`.

Example usage:
```python
sword = Object.create(session=None, name="Iron Sword", desc="A rusty blade.", is_item=True)
```

### 2.1.3 The Hook System (`at_*` methods)
Atheriz relies heavily on a hook architecture. Methods beginning with `at_` signal lifecycle and interaction events. Hooks prefixed with `at_pre_` can typically cancel an action by returning `False`.

- **Lifecycle**: `at_create`, `at_init`, `at_delete`, `at_disconnect`
- **Movement**: `at_pre_move`, `at_post_move`
- **Interaction**: `at_look`, `at_desc`, `at_get`, `at_pre_get`, `at_drop`, `at_pre_drop`, `at_give`, `at_pre_give`, `at_say`, `at_pre_say`
- **Messaging**: `at_msg_send`, `at_msg_receive`
- **Time**: `at_tick`, `at_alarm`, `at_solar_event`, `at_lunar_event`
- **Map**: `at_map_update`, `at_legend_update`, `at_pre_map_render`
- **Puppet**: `at_post_puppet`

By utilizing the `@hookable` decorator, external scripts can intercept and augment these hooks.

### 2.1.4 Object Contents & Inventory
An object's contents are managed using the internal `_contents` list and modified by methods like `add_object()`, `add_objects()`, and `remove_object()`.

The `location` attribute designates parent-child relationships. An object's location is either another `Object` (acting as a container, such as a backpack holding a sword) or a `Node` (representing the physical room the object resides in).

### 2.1.5 Searching for Objects
Locating objects depends on search requirements.

- `Object.search(query)`: Matches against names and aliases locally for a given object or room.
- `filter_by()`: A global cache filtering function found in `atheriz.singletons.objects`. Ideal for complex or comprehensive querying.
  ```python
  from atheriz.singletons.objects import filter_by
  merchants = filter_by(lambda x: x.is_npc and x.name == "Merchant")
  ```
- `get()`: Used for direct ID-based lookups from the global cache.

### 2.1.6 Messaging
Text is delivered to players through the messaging system.
- `Object.msg(text)`: Transmits data strictly to the player controlling that specific `Object`.
- `Node.msg_contents(text)`: Broadcasts text to all objects present within a room.

Atheriz includes `FuncParser`, allowing for actor-stance string interpolation (e.g., `$You()`, `$conj()`).
```python
node.msg_contents("$You() $conj(swing) the sword.", from_obj=attacker)
```
The attacker sees "You swing the sword", while onlookers read "Bob swings the sword". Refer to [`atheriz/objects/funcparser.py`](../atheriz/objects/funcparser.py) for all supported inline functions.

### 2.1.7 The `appearance_template`
When players use the `look` command on an object, the visual output is managed by the `appearance_template` string assigned on the `Object` class. This string utilizes standard format variables such as `{name}`, `{desc}`, and `{things}`. Complete formatting logic can be bypassed and reconstructed by overriding the `format_appearance()` method.

## 2.2 Nodes (Rooms)

### 2.2.1 What is a Node?
A `Node` represents a discrete room or map location. It holds spatial coordinates defined as `(area_string, x_int, y_int, z_int)`. Key properties involve `coord`, `desc`, `theme`, `symbol`, `legend_desc`, arbitrary `data`, and connected `links`. View `Node.__init__` in [`atheriz/objects/nodes.py`](../atheriz/objects/nodes.py) for specific details.

### 2.2.2 NodeLinks (Exits)
Room exits are defined by `NodeLink` objects containing a `name`, destination `coord`, and an array of `aliases`. When a player enters a node, its links are dynamically parsed into actionable commands.
```python
NodeLink("North", ("forest", 0, 1, 0), aliases=["n"])
```

### 2.2.3 Node Hooks
Nodes utilize event hooks similarly to Objects. Significant room hooks include `at_pre_object_receive`, `at_object_receive`, `at_pre_object_leave`, `at_object_leave`, `at_init`, `at_tick`, `at_desc`, and `at_delete`. Overriding `at_object_receive` is commonly used to announce a player's arrival or enforce room mechanics.

### 2.2.4 The Map System
Atheriz auto-generates a map based on node coordinates and specific node attributes. The `symbol` property dictates the visual representation on the map, and the `is_mapable` flag toggles visibility entirely. Map configuration is managed via settings such as `MAP_ENABLED`, `MAP_FPS_LIMIT`, `MAX_OBJECTS_PER_LEGEND`, and `DEFAULT_ROOM_OUTLINE`. Specific hooks like `at_map_update` allow for on-the-fly display modifications. For deep rendering mechanics, observe [`atheriz/singletons/map.py`](../atheriz/singletons/map.py).

## 2.3 Accounts

### 2.3.1 What is an Account?
An `Account` instances the user credential data out-of-band from their gameplay characters. A single account can own multiple character entities (Objects). Primary tracking attributes are `name`, password hash, the `characters` list (containing Object IDs), and `is_banned`.

See [`atheriz/objects/base_account.py`](../atheriz/objects/base_account.py) for full implementation details.

### 2.3.2 Account Lifecycle
- Execution hooks: `at_create`, `at_delete`, `at_pre_puppet`, `at_disconnect`.
- Registration and auth: `Account.create(name, password)`, `login()`, `check_password()`, `set_password()`.
- Management: `add_character()`, `remove_character()`.

Passwords are hashed utilizing SHA-256 combined with a dedicated salt (`atheriz/singletons/salt.py`).

## 2.4 Channels

### 2.4.1 What is a Channel?
A `Channel` is a basic publisher-subscriber construct that enables global or group communication streams independent of location.
Reference [`atheriz/objects/base_channel.py`](../atheriz/objects/base_channel.py) to study the structure.

### 2.4.2 Channel Methods
Objects subscribe via `subscribe()` and disconnect via `unsubscribe()`. History recording and limits for channels are governed by the `SAVE_CHANNEL_HISTORY` and `CHANNEL_HISTORY_LIMIT` directives in settings.

## 2.5 Thread Safety

### 2.5.1 Multi-threading in Atheriz
Atheriz is designed to make heavy use of multithreading, allowing thousands of objects to run `at_tick()` concurrently without slowing down the game engine. It is specifically intended to be used with Python 3.14+ free-threaded. As a consequence, game objects must manage concurrent state modifications safely.

### 2.5.2 `THREADSAFE_GETTERS_SETTERS`
By default, the setting `THREADSAFE_GETTERS_SETTERS = True` is enabled. When an Object initializes, Atheriz dynamically patches its class via `ensure_thread_safe()` (found in `atheriz/utils.py`). This overrides Python's native `__getattribute__` and `__setattr__`.

When you read or write a direct attribute on an Object (e.g., `foo.health = 10` or `print(foo.name)`), Atheriz automatically acquires the object's internal reentrant lock (`self.lock`), performs the operation, updates the `is_modified` flag so the save code knows to save the object, and releases the lock. For primitive types (integers, strings, booleans), this makes thread-safety automatic—you just use them like normal.

### 2.5.3 Working with Mutable Types (Dicts & Lists)
The automatic thread-safety patch **only triggers on assignment to the object itself**, not when you modify a mutable type already inside an attribute. If you have a dictionary attribute `foo.inventory_dict`, executing `foo.inventory_dict['sword'] = True` is **not thread-safe** and will not trigger the `is_modified` flag correctly.

When modifying lists or dicts attached to an Object, you must manually acquire the object's lock and handle the assignment correctly.

**Correct Method 1 (Reassignment):**
```python
with foo.lock:
    d = foo.bar
    d['key'] = "new_value"
    foo.bar = d  # Reassignment triggers __setattr__, handling is_modified automatically
```

**Correct Method 2 (Manual Flagging):**
```python
with foo.lock:
    foo.bar['key'] = "new_value"
    foo.is_modified = True  # Manually telling the database this object changed
```

**Incorrect (Dangerous):**
```python
foo.bar['key'] = "new_value"  # NOT THREAD-SAFE! May corrupt data and will fail to save.
```

### 2.5.4 Understanding RLocks (`self.lock`)
Every standard entity (`Object`, `Node`, `Account`, etc.) initializes with `self.lock = RLock()` from Python's `threading` library. A Reentrant Lock (RLock) means that the same thread can acquire the lock multiple times without deadlocking itself. If your custom method acquires `self.lock`, and then calls another method on the same object that also acquires `self.lock`, execution proceeds safely. However, modifying or moving *multiple* objects simultaneously requires locking every object involved in a consistent order to prevent deadlocks (see `sort_locks` inside `Object.move_to()`).

---
[Table of Contents](./table_of_contents.md) | [Next: 03 Command System](./03_command_system.md)
