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
- `WEBSOCKET_MAX_MESSAGE_SIZE`: The maximum size in bytes of a single incoming WebSocket message.
- `TELNET_ENABLED`: If `True`, enables the telnet server.
- `TELNET_PORT`: The port the telnet server listens on.
- `TELNET_INTERFACE`: The network interface to bind the telnet server to (e.g., `"0.0.0.0"` for all IPv4 or `"::"` for all IPv6/dual-stack).
- `TELNET_CONNECTION_TIMEOUT`: Seconds a telnet connection may sit idle before being disconnected.
- `TELNET_TLS_ENABLED`: If `True`, serves the telnet port over TLS
  (TELNETS) using `SSL_CERTFILE`/`SSL_KEYFILE`. Plaintext telnet clients are
  auto-detected and keep working on the same port. See
  [16 SSL/TLS & Reverse Proxying](./16_ssl_tls.md).
- `TELNET_NAWS_MIN_COLS` / `TELNET_NAWS_MAX_COLS` / `TELNET_NAWS_MIN_ROWS` / `TELNET_NAWS_MAX_ROWS`: Clamp the terminal size reported by telnet clients via NAWS.
- `NETWORK_PROTOCOLS`: The list of protocol classes the server starts (websocket and telnet).
- `STRIP_INPUT_ESCAPE_SEQUENCES`: If `True`, strips terminal escape sequences (CSI/OSC, null bytes) from player input before dispatch.
- `TERM_SIZE_MAX_WIDTH` / `TERM_SIZE_MAX_HEIGHT`: Upper bounds for the reported terminal size.
- `MAP_SIZE_MAX_WIDTH` / `MAP_SIZE_MAX_HEIGHT`: Upper bounds for the reported map-pane size.
- `WEBSERVER_ENABLED`: If `True`, hosts a web server for HTTP traffic.
- `WEBSERVER_PORT`: The integer port where the web server listens (e.g., `8000`).
- `WEBSERVER_INTERFACE`: The network interface to bind the web server to (e.g., `"0.0.0.0"` for all IPv4 or `"::"` for all IPv6/dual-stack).
- `SSL_CERTFILE`: Path to the TLS certificate file. Setting this enables the
  web server (and its `/ws` WebSocket endpoint) to serve `https`/`wss`
  instead of `http`/`ws`. **This is the only setting required** when the cert
  file is a combined PEM containing the certificate and its private key
  (common with single-file downloads). Overridable via the
  `ATHERIZ_SSL_CERTFILE` environment variable. Defaults to `None` (no TLS).
  See [16 SSL/TLS & Reverse Proxying](./16_ssl_tls.md) for a full guide,
  including the Caddy/nginx proxy alternatives.
- `SSL_KEYFILE`: Path to the TLS private key file. Optional — only needed if
  the key is stored separately from the certificate. Overridable via the
  `ATHERIZ_SSL_KEYFILE` environment variable. Defaults to `None`.

### 6.2.2 System & Core Mechanics
- `MAX_CHARACTERS`: Maximum number of characters allowed per account.
- `DEFAULT_HOME`: The default `Coord` coordinates where players spawn or respawn.
- `DEFAULT_TICK_SECONDS`: How often the game loop ticks for objects with `is_tickable = True`.
- `AUTO_COMMAND_ALIASING`: If `True`, automatically prefixes matches for player commands (e.g., typing `exa` correctly triggers `examine`).
- `THREADPOOL_LIMIT`: Maximum number of threads to use in the threadpool (defaults to system CPU count).
- `THREADPOOL_QUEUE_LIMIT`: Maximum number of pending tasks in the threadpool queue; when full, new tasks are rejected rather than queued.
- `CONNECTION_INPUT_QUEUE_LIMIT`: Maximum number of pending input messages per connection; beyond this the newest input is dropped.
- `MAX_SEARCH_DEPTH`: Maximum recursion depth when searching nested containers (guards against stack overflow).
- `THREADSAFE_GETTERS_SETTERS`: If `True`, applies thread-safe property locks on attributes. Disabling this may cause race conditions.
- `SLOW_LOCKS`: Set to `True` if you plan on changing object permission locks while they are in use. If you only set locks at object creation, you can set this to `False` for better performance.
- `Privilege`: An `IntEnum` of permission levels — `Guest`, `Player`, `Helper`, `Builder`, `Admin` — ordered from least to most privileged. Permission gates such as `is_builder` and `is_superuser` are derived from it.

### 6.2.3 Accounts & Security
- `ACCOUNT_CREATION_ENABLED`: Allows new accounts to be created from the client.
- `CHAR_CREATION_ENABLED`: Allows logged-in accounts to create new characters from the client (via the `new` command).
- `GUEST_ENABLED`: Allows guests to connect without an account.
- `GUEST_CREATION_COOLDOWN`: Minimum seconds between successful guest character creations from one host.
- `MAX_LOGIN_ATTEMPTS`: Maximum failed login attempts before a temporary ban.
- `LOGIN_ATTEMPT_COOLDOWN`: Cooldown duration in seconds for a temporary ban.

### 6.2.4 Debugging & Logging
- `DEBUG`: If `True`, prints tracebacks directly to the client in-game when errors occur.
- `LOG_LEVEL`: Determines the severity of logs to process (e.g., `"debug"`, `"info"`, `"warning"`, `"error"`, `"critical"`). Level `"debug"` logs all commands sent and received.

### 6.2.5 Persistence & Saving
- `SAVE_PATH`: Directory path for server save data and database storage. See [05 Persistence §5.1.4](./05_persistence.md#514-trust-model) — contents are fully trusted and `dill.loads` on tampered blobs is RCE; protect `save/` like credentials (`chmod 700`).
- `SECRET_PATH`: Directory path for storing sensitive information. See [05 Persistence §5.1.4](./05_persistence.md#514-trust-model) — `secret/salt.txt` and `secret/admin.token` are trusted secrets; protect `secret/` like credentials (`chmod 700`, `600` for files).
- `ALWAYS_SAVE_ALL`: If `True`, overrides the standard `is_modified` parameter check, forcing everything to be saved whether it has changed or not.
- `AUTOSAVE_PLAYERS_ON_DISCONNECT`: If `True`, saves player objects when they log out or disconnect.
- `AUTOSAVE_ON_SHUTDOWN`: If `True`, saves the game state when the server smoothly shuts down.
- `AUTOSAVE_ON_RELOAD`: If `True`, saves the game state before executing a hot reload.
- `AUTOSAVE_MINUTES`: Interval in minutes between automatic saves of the whole game state (`0` disables the interval autosave).

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

### 6.2.10 Sound Settings
- `DEFAULT_OPEN_SOUND_ATTENUATION`: Decibels subtracted from a sound each time it passes through an open pathway (e.g., open doors, hallways). Default `10.0`.
- `DEFAULT_ENCLOSED_SOUND_ATTENUATION`: Decibels subtracted from a sound each time it passes through a closed/enclosed pathway. Default `20.0`.
- `DEFAULT_AMBIENT_SOUND_LEVEL`: Ambient noise floor in decibels; incoming sounds quieter than this are ignored. Default `5.0`.

[Table of Contents](./table_of_contents.md) | [Next: 07 Mixins](./07_mixins.md)
