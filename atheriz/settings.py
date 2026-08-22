import os
from enum import IntEnum, auto
from atheriz.coord import Coord

# directory for save files
SAVE_PATH = "save"
# directory for secret files (salt, tokens)
SECRET_PATH = "secret"
# display name of the server
SERVERNAME = "AtheriZ"
# hostname advertised to clients
SERVER_HOSTNAME = "localhost"
# enable websocket protocol
WEBSOCKET_ENABLED = True
# maximum websocket message size in bytes
WEBSOCKET_MAX_MESSAGE_SIZE = 65536
# enable telnet protocol
TELNET_ENABLED = True
# telnet listen port
TELNET_PORT = 4444
# Use "::" to bind to all IPv6 (and often IPv4 via dual-stack) interfaces
TELNET_INTERFACE = "0.0.0.0"
# Serve TLS (TELNETS) on the same port; plaintext clients are auto-detected
# and still work. Uses SSL_CERTFILE (combined PEM ok) and SSL_KEYFILE.
TELNET_TLS_ENABLED = False
# timeout in seconds
TELNET_CONNECTION_TIMEOUT = 300
# minimum telnet NAWS columns
TELNET_NAWS_MIN_COLS = 20
# maximum telnet NAWS columns
TELNET_NAWS_MAX_COLS = 1000
# minimum telnet NAWS rows
TELNET_NAWS_MIN_ROWS = 5
# maximum telnet NAWS rows
TELNET_NAWS_MAX_ROWS = 200
# strip terminal escape sequences from input
STRIP_INPUT_ESCAPE_SEQUENCES = True
# maximum terminal width
TERM_SIZE_MAX_WIDTH = 1000
# maximum terminal height
TERM_SIZE_MAX_HEIGHT = 1000
# maximum map pane width
MAP_SIZE_MAX_WIDTH = 1000
# maximum map pane height
MAP_SIZE_MAX_HEIGHT = 1000
# dotted paths of network protocols to load
NETWORK_PROTOCOLS = [
    "atheriz.network.websocket.WebSocketProtocol",
    "atheriz.network.telnet.TelnetProtocol",
]
# allow new account creation
ACCOUNT_CREATION_ENABLED = True
# allow new character creation
CHAR_CREATION_ENABLED = True
# enable built-in webserver
WEBSERVER_ENABLED = True
# webserver listen port
WEBSERVER_PORT = 9999
# Use "::" to bind to all IPv6 (and often IPv4 via dual-stack) interfaces
WEBSERVER_INTERFACE = "0.0.0.0"
# paths for SSL cert and key. leave unset for no SSL
# if you have combined key/cert just set the certfile
SSL_CERTFILE = os.getenv("ATHERIZ_SSL_CERTFILE")
SSL_KEYFILE = os.getenv("ATHERIZ_SSL_KEYFILE")
# warn when game webclient differs from engine on startup
WEBCLIENT_SYNC_CHECK = True
# maximum fixed worker threads; defaults to cpu count
THREADPOOL_LIMIT = os.cpu_count()
# maximum relief threads for bursts
THREADPOOL_RELIEF_LIMIT = os.cpu_count() or 4
# seconds pool stays saturated before warning
THREADPOOL_WATCHDOG_SECONDS = 30.0
# watchdog check interval in seconds
THREADPOOL_WATCHDOG_INTERVAL = 5.0
# maximum pending threadpool tasks; add_task returns False when full
THREADPOOL_QUEUE_LIMIT = 10000
# maximum pending input messages per connection; newest input is dropped beyond this
CONNECTION_INPUT_QUEUE_LIMIT = 100
# maximum characters per account
MAX_CHARACTERS = 5
# default interval between at_tick calls in seconds
DEFAULT_TICK_SECONDS = 1.0
# sound related settings
# NOTE: these are just defaults, each room can override these
# default sound attenuation in decibels for enclosed rooms
# this should probably be higher for more realism, but sound is fun
# decrease this number to make sounds travel further
DEFAULT_ENCLOSED_SOUND_ATTENUATION = 20.0
# default sound attenuation in decibels for open rooms
# i.e. open door, hallway, forest, etc.
DEFAULT_OPEN_SOUND_ATTENUATION = 10.0
# default ambient sound level in decibels
# if incoming sounds are lower than the room's ambient level, they will be ignored
DEFAULT_AMBIENT_SOUND_LEVEL = 5.0

# only change these if you know what you're doing
class Privilege(IntEnum):
    Guest = auto()
    Player = auto()
    Helper = auto()
    Builder = auto()
    Admin = auto()


# allow guests to connect without an account?
GUEST_ENABLED = True
# start character for funcparser inline calls
FUNCPARSER_START_CHAR = "$"
# escape character for funcparser
FUNCPARSER_ESCAPE_CHAR = "\\"
# maximum funcparser nesting depth
FUNCPARSER_MAX_NESTING = 20
# max recursion depth when searching nested containers; guards against stack overflow
MAX_SEARCH_DEPTH = 100
# maximum iterations for A* pathfinding; aborts with no path if exceeded — guards against CPU exhaustion on large worlds
MAX_ASTAR_ITERATIONS = 50000
# default client terminal width
CLIENT_DEFAULT_WIDTH = 78
# default client terminal height
CLIENT_DEFAULT_HEIGHT = 45
# print exceptions in-game
DEBUG = True
# possible values: debug, info, warning, error, critical
# log level debug will log all commands sent and received
LOG_LEVEL = "info"
# persist channel history to database
SAVE_CHANNEL_HISTORY = True
# maximum channel history entries to keep
CHANNEL_HISTORY_LIMIT = 50
# If you plan on changing object permission locks while they are in use, set this to True
# If you only set locks at object creation, you can set this to False
SLOW_LOCKS = True
# Max attempts before temporary ban
MAX_LOGIN_ATTEMPTS = 3
# Cooldown in seconds for temporary ban
LOGIN_ATTEMPT_COOLDOWN = 100
# Max simultaneous connections per client IP (0 = unlimited)
MAX_CONNECTIONS_PER_IP = 2
# seconds to wait for a menu prompt before giving up
MENU_PROMPT_TIMEOUT = 60
# Minimum time in seconds between successful guest/account/character creations from one host
CREATION_COOLDOWN = 60
# minutes before a mapedit chain expires and is evicted; 0 disables eviction
MAPEDIT_CHAIN_TTL = 180.0
# maximum number of live mapedit chains; oldest evicted first
MAPEDIT_MAX_CHAINS = 256
# maximum length for account names
MAX_ACCOUNT_NAME_LENGTH = 20
# maximum length for character names
MAX_CHARACTER_NAME_LENGTH = 20
# minimum length for passwords
MIN_PASSWORD_LENGTH = 8
# maximum length for passwords — bounds hashing cost
MAX_PASSWORD_LENGTH = 1024
# if true, save all objects instead of only modified ones
ALWAYS_SAVE_ALL = False
# default home location for new characters
DEFAULT_HOME = Coord("limbo", 4, 4, 4)
# enable map system
MAP_ENABLED = True
# enable map legend
LEGEND_ENABLED = True
# maximum frames per second for map rendering, recommended to be around 5-10
MAP_FPS_LIMIT = 5
# no map legend will be shown if there are more mapable objects than this
MAX_OBJECTS_PER_LEGEND = 30
# autosave players on disconnect
AUTOSAVE_PLAYERS_ON_DISCONNECT = True
# autosave on shutdown
AUTOSAVE_ON_SHUTDOWN = True
# autosave on reload
AUTOSAVE_ON_RELOAD = True
# interval in minutes (float). 0 = disabled.
AUTOSAVE_MINUTES = 0
# if true, will match command to beginning of available commands
# for instance, player enters "exa" and "examine" is found, it will run examine
# uses str.startswith() to find matching commands
AUTO_COMMAND_ALIASING = True
# keys the resolver refuses to auto-alias (inputfuncs) and the "did you mean?"
# fallback refuses to suggest (none.py); single source for both blocklists
AUTO_ALIAS_IGNORED_KEYS = ["save", "quit", "wander", "exit", "logout", "disconnect", "none"]
# if true, will use thread-safe getters and setters for attributes
# this slows down attribute access but makes thread-safety much easier
# if you disable this, you'll probably run into thread-safety issues because core code is relying on this
# note: this doesn't work for mutable attributes like lists and dicts, you'll need to manually lock those
THREADSAFE_GETTERS_SETTERS = True
# possible values: single, double, rounded, none
DEFAULT_ROOM_OUTLINE = "single"
# choose characters for these which will never be used on a map
# using these characters in a custom map will cause rendering errors
SINGLE_WALL_PLACEHOLDER = "༗"
DOUBLE_WALL_PLACEHOLDER = "༁"
ROUNDED_WALL_PLACEHOLDER = "⍮"
ROOM_PLACEHOLDER = "℣"
PATH_PLACEHOLDER = "߶"
ROAD_PLACEHOLDER = "᭤"
# all symbols which can be rendered as a different shape according to neighbors
ALL_SYMBOLS = [
    SINGLE_WALL_PLACEHOLDER,
    DOUBLE_WALL_PLACEHOLDER,
    ROUNDED_WALL_PLACEHOLDER,
    PATH_PLACEHOLDER,
    ROAD_PLACEHOLDER,
]
# brown doors:
NS_CLOSED_DOOR = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m━\x1b[0m"
NS_OPEN_DOOR1 = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┚\x1b[0m"
NS_OPEN_DOOR2 = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┒\x1b[0m"
EW_CLOSED_DOOR = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┃\x1b[0m"
EW_OPEN_DOOR1 = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┙\x1b[0m"
EW_OPEN_DOOR2 = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┕\x1b[0m"
UD_CLOSED_DOOR = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m╳\x1b[0m"
UD_OPEN_DOOR = "\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m▽\x1b[0m"
# --- time related settings ---
# enable in-game time system
TIME_SYSTEM_ENABLED = True
# choose which objects receive sunrise, sunset messages
# if you want all objects to receive these messages, set this to: lambda x: True
# if you want no objects to receive these messages, set this to: lambda x: False
# if you want PCs and NPCs to receive them: lambda x: (x.is_pc and x.is_connected) or x.is_npc
# these are based on the flags defined in flags.py
SOLAR_RECEIVER_LAMBDA = lambda x: x.is_pc and x.is_connected
# choose which objects receive moon phase messages
LUNAR_RECEIVER_LAMBDA = lambda x: x.is_pc and x.is_connected
# seconds between time updates
# this is the resolution of the time system
# every N seconds below, the time will advance by TICK_MINUTES below
TIME_UPDATE_SECONDS = 1.0
# starting in-game year
START_YEAR = 888
# minutes the clock should advance for every update tick above
TICK_MINUTES = 1.0
# seconds per minute
SECONDS_PER_MINUTE = 60
# minutes per hour
MINUTES_PER_HOUR = 60
# hours per day
HOURS_PER_DAY = 24
# days per month
DAYS_PER_MONTH = 30
# months per year
MONTHS_PER_YEAR = 12
# days per year
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR
# seconds per hour
SECONDS_PER_HOUR = SECONDS_PER_MINUTE * MINUTES_PER_HOUR
# seconds per day
SECONDS_PER_DAY = SECONDS_PER_HOUR * HOURS_PER_DAY
# days per lunar cycle
LUNAR_CYCLE_DAYS = 30
# days per week
DAYS_PER_WEEK = 7
# 6 AM
SUNRISE_HOUR = 6
# 6 PM
SUNSET_HOUR = 18
# message on sunrise
SUNRISE_MESSAGE = "The sun rises on a new day."
# message on sunset
SUNSET_MESSAGE = "The sun begins to set."


class Month(IntEnum):
    Ianuarius = 1
    Februarius = 2
    Martius = 3
    Aprilis = 4
    Maius = 5
    Iunius = 6
    Iulius = 7
    Augustus = 8
    September = 9
    October = 10
    November = 11
    December = 12

# mapping of decibels to description

LOUDNESS_LEVELS = (
    (20, " nearly inaudible"),
    (40, " faint"),
    (60, ""),
    (80, " loud"),
    (100, " very loud"),
    (120, " extremely loud"),
)

# percentage of words to replace with "..." at certain decibel levels
# first number is decibels, second is percentage
REPLACE_LEVELS = (
    (1, 95.0),
    (10, 80.0),
    (20, 60.0),
    (30, 40.0),
    (40, 20.0),
    (50, 10.0),
)

# --- `py` admin command sandbox ---
# maximum lines of combined output (captured stdout + result) sent to the caller
PY_MAX_OUTPUT_LINES = 200
# maximum bytes of combined output sent to the caller
PY_MAX_OUTPUT_BYTES = 50_000
# xterm256 foreground color used to colorize the `py` command's output
# 15 is standard bright white
PY_OUTPUT_FG = 15
# seconds a `py` command may run before its thread is force-killed;
# 0 disables the timeout (commands run to completion)
KILL_PY_COMMAND_AFTER = 5
# maximum source size (utf-8 bytes) accepted by the py sandbox
PY_MAX_CODE_BYTES = 65_536
# maximum number of AST nodes accepted by the py sandbox
PY_MAX_AST_NODES = 20_000
# maximum traced line events before a py run is killed (CPU budget)
PY_MAX_LINE_EVENTS = 5_000_000
# when True, py requires superuser instead of builder privileges
PY_REQUIRE_SUPERUSER = False
