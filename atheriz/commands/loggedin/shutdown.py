#
from atheriz.commands.base_cmd import Command
from atheriz import settings
from pathlib import Path
from typing import TYPE_CHECKING
import urllib.request
import urllib.error
import json

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
try:
    import server_events
    import importlib

    importlib.reload(server_events)
except ImportError:
    import atheriz.server_events as server_events


class ShutdownCommand(Command):
    key = "shutdown"
    category = "Admin"
    desc = "Shutdown the server."
    hide = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_superuser

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.msg("Initiating server shutdown...")
        server_events.at_server_stop()

        port = settings.WEBSERVER_PORT
        secret_path = Path(settings.SECRET_PATH)
        token_file = secret_path / "admin.token"

        if not token_file.exists():
            caller.msg("Error: admin.token not found.")
            return

        try:
            with open(token_file, "r") as f:
                token = f.read().strip()
        except Exception as e:
            caller.msg(f"Error reading token: {e}")
            return

        url = f"http://localhost:{port}/_internal/shutdown"
        req = urllib.request.Request(url, method="POST")
        req.add_header("X-Admin-Token", token)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    if data.get("status") == "ok":
                        caller.msg("Server shutdown initiated successfully.")
                    else:
                        caller.msg(f"Shutdown failed: {data.get('message')}")
                else:
                    caller.msg(f"Shutdown failed with HTTP {response.status}")
        except urllib.error.URLError as e:
            caller.msg(f"Error connecting to shutdown endpoint: {e}")
        except Exception as e:
            caller.msg(f"Shutdown error: {e}")
