# 04 Scripts & the Hook System

## 4.1 What is a Script?

### 4.1.1 Overview
A `Script` is an entity that attaches to an `Object` or `Node` and intercepts its `at_*` lifecycle and interaction hooks. Scripts provide the primary mechanism for composition and reusability within Atheriz, allowing you to layer dynamic behaviors on objects and rooms without requiring complex class inheritance structures.

Common uses include timed buffs/debuffs, complex AI behaviors, localized weather effects, quest tracking, temporary status alterations, and dynamic room behaviors.

Reference [`atheriz/objects/base_script.py`](../atheriz/objects/base_script.py) for the core definitions.

### 4.1.2 Script Lifecycle
1. **Creation**: Calling `Script.create(caller, name, desc)` instantiates the script and caches it in memory.
2. **Installation**: Calling `obj.add_script(script)` / `node.add_script(script)` calls `script.install_hooks(child)` (`atheriz/objects/base_script.py:183`, `base_obj.py:205`, `nodes.py:589`) which patches the script's `at_*` hooks onto the child and calls `at_install()`.
3. **Execution**: Hooks are stored in `child.hooks[method]` sets; `hookable` wrapper in `base_obj.py:46` runs `@replace` (first only) or `before → original → after` (after can mutate return via `result = h(...)` `63`).
4. **Removal**: `obj.remove_script(script)` / `Script.delete(caller)` removes hooks via `remove_hooks` and deletes the Script. `resolve_relations` re-installs hooks on every reboot (`base_obj.py:508`, `nodes.py:197`) so `at_install` must be idempotent.

## 4.2 Hook Decorators: `@before`, `@after`, `@replace`

### 4.2.1 How Hooks Work
Any method contained inside a Script subclass designated with the `at_` prefix acts as an interception hook upon the child Object.

Every `at_*` method inside a script **must** use one decorator from `atheriz.objects.base_script`:
- `@before`: Runs before the original; return value discarded (`base_obj.py:57`), original always runs afterward, cannot cancel.
- `@after`: Runs after the original (`base_obj.py:63`) as `result = h(*args, **kwargs)` — may transform the return value.
- `@replace`: Skips original and other hooks; only the *first* `@replace` runs if multiple are registered (`base_obj.py:53`).

Undecorated hooks in a `hooks[func]` set raise `ValueError` (`base_obj.py:67`). The `is_before/is_after/is_replace` flags connect into `@hookable` (`base_obj.py:46`).

### 4.2.2 Node Hooks
Node hooks function identically to Object hooks. Any `at_*` method on a `Node` can be intercepted by a script using the same decorators. Common node hooks include:

- `at_tick` — Called every tick on the node.
- `at_init` — Called after deserialization when the node is re-linked.
- `at_pre_object_leave` / `at_object_leave` — Called before/after an object leaves the node.
- `at_pre_object_receive` / `at_object_receive` — Called before/after an object enters the node.
- `at_desc` — Called when the node is looked at.
- `at_hear` — Called when a sound reaches the node.
- `at_delete` — Called before the node is deleted.

### 4.2.3 Practical Examples

**@before**: Creating a damage-over-time tick effect that reduces health before an object processes a tick normally.

```python
from atheriz.objects.base_script import Script, before

class PoisonScript(Script):
    @before
    def at_tick(self):
        self.child.health -= 5
```

**@after**: A diagnostics script tracking object movement passively.

```python
from atheriz.objects.base_script import Script, after

class TrackingScript(Script):
    @after
    def at_post_move(self, destination, to_exit=None, **kwargs):
        print(f"Object {self.child.id} moved to {destination}")
```

**@replace**: A paralyze script preventing movement execution entirely.

```python
from atheriz.objects.base_script import Script, replace

class FrozenScript(Script):
    @replace
    def at_pre_move(self, destination):
        self.child.msg("You are completely frozen and cannot move.")
        return False
```

**Node @replace**: A gravity well node that prevents objects from leaving.

```python
from atheriz.objects.base_script import Script, replace

class GravityWellScript(Script):
    @replace
    def at_pre_object_leave(self, destination, to_exit=None, **kwargs):
        # Node has no .msg — use msg_contents or iterate contents
        self.child.msg_contents("The gravity well holds you firmly in place.")
        return False
```

**Node @after**: A trap node that triggers when something enters.

```python
from atheriz.objects.base_script import Script, after

class SpikeTrapScript(Script):
    @after
    def at_object_receive(self, source, from_exit=None, **kwargs):
        for obj in self.child.contents:
            if obj.is_pc or obj.is_npc:
                obj.msg("Spikes shoot from the floor! You take damage.")
```

## 4.3 Creating a Custom Script

### 4.3.1 Step-by-Step: A Buff Script
A strength buff script alters an object's combat calculations for multiple ticks, eliminating itself after the duration lapses.

```python
from atheriz.objects.base_script import Script, after

class StrengthBuff(Script):
    def at_install(self):
        self.duration = 10
        self.child.strength_modifier += 5
        self.child.msg("You feel immense strength surging through you.")

    @after
    def at_tick(self):
        self.duration -= 1
        if self.duration <= 0:
            self.child.msg("Your strength fades.")
            self.child.strength_modifier -= 5
            self.delete()
            return
```

### 4.3.2 Real World Example: The Follow Script

For a practical example of custom script usage, see [`atheriz/commands/loggedin/follow.py`](../atheriz/commands/loggedin/follow.py). 

The `FollowScript` showcases two very important script concepts:

- **The `self.is_temporary` flag**: By setting `self.is_temporary = True` *after* `super().__init__()` in `__init__` (since `Flags.__init__` sets it `False`, `atheriz/objects/base_flags.py:18`; e.g. `follow.py:13`), you instruct `save_objects` to skip persistence (`atheriz/globals/objects.py:271`). Only lives in memory and clears on restart.
- **The `self.child` reference**: During hook execution, `self.child` provides a direct reference to the parent `Object` or `Node` the script is attached to. This allows the script to neatly access or modify the child object's properties natively (e.g., examining `self.child.followers`, `self.child.location`, or `self.child.contents` for nodes).

### 4.3.3 Attaching and Removing Scripts
Assigning scripts to target objects or nodes utilizes standard API methods:
- `object.add_script(script_or_id)`
- `object.remove_script(script_or_id)`
- `node.add_script(script_or_id)`
- `node.remove_script(script_or_id)`

### 4.3.4 Checking for Scripts
Checking for scripts is done using the `has_script_type()` method (on `Object` only; `Node` has `add_script`/`remove_script` only, `nodes.py:589`):
- `object.has_script_type(script_type)` (`atheriz/objects/base_obj.py:237`)

### 4.3.5 Getting Scripts by Type
Getting scripts of a specific type is done using the `get_scripts_by_type()` method (on `Object` only):
- `object.get_scripts_by_type(script_type)` (`atheriz/objects/base_obj.py:257`) — inspect `node.scripts` set or use `filter_by` for nodes

### 4.3.6 Node Scripts
Nodes support the same script attachment API as Objects. When a script is attached to a node, its `at_*` hooks intercept the node's native lifecycle methods. This is useful for creating dynamic room behaviors, traps, environmental hazards, or buff/debuff zones.

```python
from atheriz.objects.nodes import Node
from atheriz.objects.base_script import Script, before

class HealingAuraScript(Script):
    @before
    def at_tick(self):
        for obj in self.child.contents:
            if getattr(obj, "is_pc", False):
                obj.health = min(obj.max_health, getattr(obj, "health", 0) + 2)

# Create a node and attach the script
from atheriz.utils import Coord
room = Node(coord=Coord("forest", 5, 5, 0), desc="A warm, soothing grove.")
room.add_script(HealingAuraScript.create(None, "HealingAura"))
```

[Table of Contents](./table_of_contents.md) | [Next: 05 Persistence](./05_persistence.md)
