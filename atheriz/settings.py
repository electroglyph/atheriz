import os

SAVE_PATH = "save"
SECRET_PATH = "secret"
SERVERNAME = "AtheriZ"
SERVER_HOSTNAME = "localhost"
WEBSOCKET_ENABLED = True
ACCOUNT_CREATION_ENABLED = True
WEBSERVER_ENABLED = True
WEBSERVER_PORT = 8000
WEBSERVER_INTERFACE = "0.0.0.0"
THREADPOOL_LIMIT = os.cpu_count()
MAX_CHARACTERS = 2
PERMISSION_HIERARCHY = [
    0,  # Guest, note-only used if GUEST_ENABLED=True
    1,  # Player
    2,  # Helper
    3,  # Builder
    4,  # Admin
]
# If True, will allow guest characters to be created (not implemented yet)
# GUEST_ENABLED = True
FUNCPARSER_START_CHAR = "$"
FUNCPARSER_ESCAPE_CHAR = "\\"
FUNCPARSER_MAX_NESTING = 20
CLIENT_DEFAULT_WIDTH = 78
CLIENT_DEFAULT_HEIGHT = 45
# print exceptions in-game
DEBUG = True
# possible values: debug, info, warning, error, critical
# log level debug will log all commands sent and received
LOG_LEVEL = "info"
SAVE_CHANNEL_HISTORY = True
CHANNEL_HISTORY_LIMIT = 50
# If you plan on changing object permission locks while they are in use, set this to True
# If you only set locks at object creation, you can set this to False
SLOW_LOCKS = True
# Max attempts before temporary ban
MAX_LOGIN_ATTEMPTS = 3
# Cooldown in seconds for temporary ban
LOGIN_ATTEMPT_COOLDOWN = 100
DEFAULT_HOME = ("limbo", 0, 0, 0)
MAP_ENABLED = True
LEGEND_ENABLED = True
# maximum frames per second for map rendering, recommended to be around 5-10
MAP_FPS_LIMIT = 5
# no map legend will be shown if there are more mapable objects than this
MAX_OBJECTS_PER_LEGEND = 30
AUTOSAVE_PLAYERS_ON_DISCONNECT = True
AUTOSAVE_ON_SHUTDOWN = True
AUTOSAVE_ON_RELOAD = True
# if true, will match command to beginning of available commands
# for instance, player enters "exa" and "examine" is found, it will run examine
# uses str.startswith() to find matching commands
AUTO_COMMAND_ALIASING = True
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
