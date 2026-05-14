# 06 Settings & Configuration

## 6.1 How Settings Work

### 6.1.1 The Import Chain
Game folders import and override core settings by importing `atheriz.settings` and redefining variables. Your game's `settings.py` file executes `from atheriz.settings import *` to get the base settings, and then you can redefine variables to override them. See [`atheriz/settings.py`](../atheriz/settings.py) for the default settings.

### 6.1.2 `CLASS_INJECTIONS` (The Most Important Setting)
Atheriz relies on a modular class replacement mechanic known as Class Injection. By adding to the `CLASS_INJECTIONS` list, you can replace default Atheriz classes with your own custom ones.

Each entry in the list is a tuple with three parts:
`(local_module, class_name, target_import_path)`

Example:
```python
CLASS_INJECTIONS = [
    ("object", "Object", "atheriz.objects.base_obj"),
]
```

This specifies: "Import the `Object` class defined inside `my_game/object.py` and use it to replace the `Object` class inside `atheriz.objects.base_obj`." This module-level monkey-patching applies uniformly, meaning all systems using the native Atheriz classes will instantly use your custom overrides instead.

## 6.2 Settings Reference

### 6.2.1 Server & Networking
- `SERVERNAME`: The display name of the game server.
- `SERVER_HOSTNAME`: The root hostname or IP address of the server.
- `WEBSOCKET_ENABLED`: If `True`, enables the WebSocket server functionality.
- `WEBSERVER_ENABLED`: If `True`, hosts a web server for HTTP traffic.
- `WEBSERVER_PORT`: The integer port where the web server listens (e.g., `8000`).
- `WEBSERVER_INTERFACE`: The network interface to bind the web server to (e.g., `"0.0.0.0"` for all IPv4 or `"::"` for all IPv6/dual-stack).

### 6.2.2 System & Core Mechanics
- `MAX_CHARACTERS`: Maximum number of characters allowed per account.
- `DEFAULT_HOME`: The default `Coord` coordinates where players spawn or respawn.
- `DEFAULT_TICK_SECONDS`: How often the game loop ticks for objects with `is_tickable = True`.
- `AUTO_COMMAND_ALIASING`: If `True`, automatically prefixes matches for player commands (e.g., typing `exa` correctly triggers `examine`).
- `THREADPOOL_LIMIT`: Maximum number of threads to use in the threadpool (defaults to system CPU count).
- `THREADSAFE_GETTERS_SETTERS`: If `True`, applies thread-safe property locks on attributes. Disabling this may cause race conditions.
- `SLOW_LOCKS`: Set to `True` if you plan on changing object permission locks while they are in use. If you only set locks at object creation, you can set this to `False` for better performance.
- `PERMISSION_HIERARCHY`: List of integers representing permission hierarchy levels (e.g., Guest, Player, Helper, Builder, Admin).

### 6.2.3 Accounts & Security
- `ACCOUNT_CREATION_ENABLED`: Allows new accounts to be created from the client.
- `MAX_LOGIN_ATTEMPTS`: Maximum failed login attempts before a temporary ban.
- `LOGIN_ATTEMPT_COOLDOWN`: Cooldown duration in seconds for a temporary ban.

### 6.2.4 Debugging & Logging
- `DEBUG`: If `True`, prints tracebacks directly to the client in-game when errors occur.
- `LOG_LEVEL`: Determines the severity of logs to process (e.g., `"debug"`, `"info"`, `"warning"`, `"error"`, `"critical"`). Level `"debug"` logs all commands sent and received.

### 6.2.5 Persistence & Saving
- `SAVE_PATH`: Directory path for server save data and database storage.
- `SECRET_PATH`: Directory path for storing sensitive information.
- `ALWAYS_SAVE_ALL`: If `True`, overrides the standard `is_modified` parameter check, forcing everything to be saved whether it has changed or not.
- `AUTOSAVE_PLAYERS_ON_DISCONNECT`: If `True`, saves player objects when they log out or disconnect.
- `AUTOSAVE_ON_SHUTDOWN`: If `True`, saves the game state when the server smoothly shuts down.
- `AUTOSAVE_ON_RELOAD`: If `True`, saves the game state before executing a hot reload.

### 6.2.6 Map & UI Settings
- `MAP_ENABLED`: Toggles the visibility of the in-game map.
- `LEGEND_ENABLED`: Toggles whether a map legend is displayed.
- `MAP_FPS_LIMIT`: Caps rendering speeds for calculations (recommended 5-10).
- `MAX_OBJECTS_PER_LEGEND`: The maximum number of objects displayed before hiding the legend.
- `DEFAULT_ROOM_OUTLINE`: Defines room border styles (e.g., `"single"`, `"double"`, `"rounded"`, `"none"`).
- `CLIENT_DEFAULT_WIDTH`: Default window width for the connected client interface.
- `CLIENT_DEFAULT_HEIGHT`: Default window height for the connected client interface.

**Map Placeholders & Rendering Symbols**
- Custom placeholders for different map elements: `SINGLE_WALL_PLACEHOLDER`, `DOUBLE_WALL_PLACEHOLDER`, `ROUNDED_WALL_PLACEHOLDER`, `ROOM_PLACEHOLDER`, `PATH_PLACEHOLDER`, `ROAD_PLACEHOLDER`.
- `ALL_SYMBOLS`: An internal reference defining characters that conditionally adapt shape according to neighboring elements.
- **Door Configurations**: Constants for defining aesthetic states in doors, including properties like `NS_CLOSED_DOOR`, `EW_OPEN_DOOR1`, etc.

### 6.2.7 Time System Settings
- `TIME_SYSTEM_ENABLED`: Toggles the time system on or off.
- `TIME_UPDATE_SECONDS`: Resolution interval in seconds detailing how regularly time calculates.
- `START_YEAR`: Starting calendar year for newly generated worlds.
- `TICK_MINUTES`: Number of in-game minutes the clock advances per real-world tick.
- `SOLAR_RECEIVER_LAMBDA` / `LUNAR_RECEIVER_LAMBDA`: Lambda functions defining which objects receive global time transitions (e.g., making sure PCs receive sunset messages).
- `SUNRISE_HOUR` / `SUNSET_HOUR`: The specific time metrics dictating day/night transitions alongside messaging hooks (`SUNRISE_MESSAGE` & `SUNSET_MESSAGE`).
- Also includes standards for chronological calculations (`SECONDS_PER_MINUTE`, `DAYS_PER_MONTH`, etc.) and a `Month` enumeration.

### 6.2.8 Channels
- `SAVE_CHANNEL_HISTORY`: If `True`, stores chat histories for communication channels.
- `CHANNEL_HISTORY_LIMIT`: Limits the number of past messages retained in channel buffers.

### 6.2.9 FuncParser Settings
- `FUNCPARSER_START_CHAR`: Defines the initialization character for invoking functions (default: `$`).
- `FUNCPARSER_ESCAPE_CHAR`: Specifies the escape character mapping (default: `\`).
- `FUNCPARSER_MAX_NESTING`: Determines the maximum level of allowed nested arguments dynamically.

[Table of Contents](./table_of_contents.md) | [Next: 07 Mixins](./07_mixins.md)
