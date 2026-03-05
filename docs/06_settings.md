# 06 Settings & Configuration

## 6.1 How Settings Work

### 6.1.1 The Import Chain
Game folders derive configuration from the parent system utilizing an override approach. Your `settings.py` file executes `from atheriz.settings import *`, subsequently replacing defaults by explicitly redefining specific variables deeper within the file. Standard Python evaluation prioritizes identical parameters declared towards the bottom of the execution trace.

### 6.1.2 `CLASS_INJECTIONS` (The Most Important Setting)
Atheriz relies exclusively on a modular class replacement mechanic known as Class Injection. By populating the `CLASS_INJECTIONS` array, the system systematically replaces base module identifiers with custom target references precisely upon system instantiation.

The array mandates a three-part tuple syntax:
`(local_module, class_name, target_import_path)`

Example:
```python
CLASS_INJECTIONS = [
    ("object", "Object", "atheriz.objects.base_obj"),
]
```

This specifies: "Import the `Object` class defined inside `my_game/object.py` and replace the `Object` execution reference stored natively inside `atheriz.objects.base_obj`." This module-level monkey-patching applies uniformly, meaning all subroutines calling native Atheriz implementations instantly receive your custom codebase overrides.

## 6.2 Settings Reference

### 6.2.1 Server Settings
- `SERVERNAME`: The designated string display identifying the core game instance.
- `SERVER_HOSTNAME`: Root networking path. 
- `WEBSOCKET_ENABLED`: Toggles core WebSocket server functionality.
- `WEBSERVER_ENABLED`: Specifies HTTP traffic hosting.
- `WEBSERVER_PORT`: Integer assignment for server hosting connections.
- `WEBSERVER_INTERFACE`: Targets strict interface binding addresses.

### 6.2.2 Gameplay Settings
- `MAX_CHARACTERS`: Identifies restrictions capping total instanced objects per valid account.
- `DEFAULT_TICK_SECONDS`: Specifies universal system iteration limits affecting objects executing `is_tickable = True`.
- `ACCOUNT_CREATION_ENABLED`: Limits external registration sequences directly from the client application.
- `DEFAULT_HOME`: Explicit `(area, x, y, z)` spatial coordinate tuple handling where players populate during reconnection or death sequences (often configured to limbs or staging nodes).
- `AUTO_COMMAND_ALIASING`: Toggle prefix matching behavior for input actions (e.g. mapping `exa` accurately to `examine`).

### 6.2.3 Map Settings
Graphical adjustments handling standard CLI renderings limit configurations natively.
- `MAP_ENABLED`: Toggle system mapping visibility entirely.
- `MAP_FPS_LIMIT`: Caps rendering speeds during heavy calculations.
- `MAX_OBJECTS_PER_LEGEND`: Designates rendering limitations displaying character readouts sequentially across adjacent UI elements.
- `DEFAULT_ROOM_OUTLINE`: Formats rendering border architectures.

Atheriz identifies visual connections systematically replacing Unicode variables automatically utilizing an `ALL_SYMBOLS` internal reference layout.

### 6.2.4 Time System Settings
Time acceleration formulas operate autonomously using real-time offsets defined dynamically.
- `TIME_SYSTEM_ENABLED`: Toggles calculation execution entirely.
- `TIME_UPDATE_SECONDS`: Configures raw iteration checks against hardware limits. Every iteration evaluates advancing the internal clock accurately matching configuring `TICK_MINUTES` equivalents.
- `SOLAR_RECEIVER_LAMBDA`: Filters precise target validations against internal server checks resolving sunrise hooks selectively across connected targets. 

### 6.2.5 Persistence & Debug Settings
- `SAVE_PATH`: Valid target directory path logging serialized blob properties.
- `ALWAYS_SAVE_ALL`: Overrides the standard `is_modified` parameter check executing comprehensive table snapshots.
- `DEBUG`: Provides complete tracebacks matching internal failures instantly to client user screens globally. Recommended strictly for localized test builds.

### 6.2.6 Threading & Performance
- `THREADPOOL_LIMIT`: Manages dynamic threading caps targeting raw HTTP routing callbacks externally processed.
- `THREADSAFE_GETTERS_SETTERS`: Patches native class variables directly ensuring multi-threaded checks evaluate strictly behind `RLock` configurations. Disabling improves execution performance significantly natively affecting synchronization safety. 

[Table of Contents](./table_of_contents.md) | [Next: 07 Mixins](./07_mixins.md)
