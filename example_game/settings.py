# Import all settings from the base game
from atheriz.settings import *

# Custom settings - add or override below
# Example:
# SERVERNAME = "My Custom Game"
# WEBSERVER_PORT = 8001
# TELNET_ENABLED = True
# TELNET_PORT = 4000
# NETWORK_PROTOCOLS = [
#     "atheriz.network.websocket.WebSocketProtocol",
#     "atheriz.network.telnet.TelnetProtocol"
# ]

# Class injection configuration
# (local_module, class_name, target_import_path)
# Class injection configuration
# (local_module, class_name, target_import_path)
CLASS_INJECTIONS = [
    ("account", "Account", "atheriz.objects.base_account"),
    ("object", "Object", "atheriz.objects.base_obj"),
    ("channel", "Channel", "atheriz.objects.base_channel"),
    ("node", "Node", "atheriz.objects.nodes"),
    ("door", "Door", "atheriz.objects.base_door"),
    ("commands.loggedin", "LoggedinCmdSet", "atheriz.commands.loggedin.cmdset"),
    ("commands.unloggedin", "UnloggedinCmdSet", "atheriz.commands.unloggedin.cmdset"),
    ("inputfuncs", "InputFuncs", "atheriz.inputfuncs"),
    ("script", "Script", "atheriz.objects.base_script"),
    # ("connection", "BaseConnection", "atheriz.network.connection"),
]

