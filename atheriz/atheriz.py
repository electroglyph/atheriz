from atheriz.singletons.objects import filter_by
from atheriz.logger import logger
import argparse
import signal
import time
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from atheriz import settings
from atheriz.websocket import websocket_endpoint, websocket_manager
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.singletons.objects import add_object, get, load_objects, save_objects
from atheriz.singletons.startstop import do_shutdown, do_startup, do_reload
from atheriz.singletons.get import get_node_handler, get_unique_id
from atheriz.database_setup import get_database
import secrets
import shutil
import atheriz.reloader as reloader
import atheriz.initial_setup as initial_setup
import traceback
import os

# global state
class ServerState:
    def __init__(self):
        self.running = False
        self.uvicorn_server = None


server_state = ServerState()

app = FastAPI(title=settings.SERVERNAME)

app.websocket("/ws")(websocket_endpoint)

# Default web directories (from atheriz package); overridden by game folder if it has a web/ dir
templates_dir = Path(__file__).parent / "web" / "templates"
static_dir = Path(__file__).parent / "web" / "static"
templates = Jinja2Templates(directory=str(templates_dir))


def get_file_version(path: str) -> str:
    """Get the modification time of a file to use as a version string."""
    try:
        file_path = static_dir / path
        if file_path.exists():
            return str(int(file_path.stat().st_mtime))
    except Exception:
        pass
    return "1"


# add the version helper to the template context
templates.env.globals["v"] = get_file_version


def setup_game_folder():
    """
    Detect if running in a game folder and inject custom classes/settings.
    Exits if not in a game folder.
    """
    import sys
    import os
    import importlib
    
    from atheriz.utils import is_in_game_folder
    
    # Check if we are in a game folder (looks for settings.py, save directory, and __init__.py)
    cwd = Path.cwd()
    if not is_in_game_folder():
        print("Error: 'atheriz start' must be run from a game folder (containing settings.py, save/, and __init__.py).")
        print(f"Current directory: {cwd}")
        sys.exit(1)

    print(f"Game folder detected at {cwd}. Injecting custom classes and settings...")
    
    # Add setup folder to sys.path
    sys.path.insert(0, str(cwd))
    
    try:
        import settings as local_settings
        # Override values in atheriz.settings
        for key in dir(local_settings):
            if key.isupper():
                setattr(settings, key, getattr(local_settings, key))
        print("  - Settings injected.")
    except ImportError as e:
        print(f"  - Error importing local settings: {e}")
        sys.exit(1)

    injections = getattr(settings, "CLASS_INJECTIONS", [])
    if not injections:
        print("  - No CLASS_INJECTIONS found in settings.")
        return

    for local_mod, cls_name, target_mod in injections:
        try:
            module = importlib.import_module(local_mod)
            if hasattr(module, cls_name):
                new_cls = getattr(module, cls_name)
                target = importlib.import_module(target_mod)
                setattr(target, cls_name, new_cls)
                print(f"  - Injected {cls_name} from {local_mod}.py")
            else:
                print(f"  - Warning: {cls_name} not found in {local_mod}.py")
        except ImportError:
            # It's okay if some custom files don't exist or aren't importable
            print(f"  - Note: Could not import {local_mod}.py (skipping injection)")
        except Exception as e:
            print(f"  - Error injecting {cls_name}: {e}")

    # Check if the game folder has a web/ directory to override templates and static files
    global templates_dir, static_dir, templates
    game_web = cwd / "web"
    if game_web.is_dir():
        game_templates = game_web / "templates"
        game_static = game_web / "static"
        if game_templates.is_dir():
            templates_dir = game_templates
            templates = Jinja2Templates(directory=str(templates_dir))
            templates.env.globals["v"] = get_file_version
            print(f"  - Using game folder templates: {game_templates}")
        if game_static.is_dir():
            static_dir = game_static
            print(f"  - Using game folder static files: {game_static}")



@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/webclient/index.html", response_class=HTMLResponse)
async def read_webclient(request: Request):
    return templates.TemplateResponse("webclient/index.html", {"request": request})


@app.post("/_internal/hot_reload")
async def hot_reload_endpoint(request: Request):
    token = request.headers.get("X-Admin-Token")

    secret_path = Path(settings.SECRET_PATH)
    token_file = secret_path / "admin.token"

    if not token_file.exists():
        return {"status": "error", "message": "Token file not found."}

    with open(token_file, "r") as f:
        expected_token = f.read().strip()

    if request.client.host not in ["127.0.0.1", "::1"]:
        return {"status": "error", "message": "Remote reload not allowed."}

    if token != expected_token:
        return {"status": "error", "message": "Invalid token."}

    do_reload()
    msg = reloader.reload_game_logic()
    return {"status": "ok", "message": msg}


@app.post("/_internal/shutdown")
async def shutdown_endpoint(request: Request):
    token = request.headers.get("X-Admin-Token")

    secret_path = Path(settings.SECRET_PATH)
    token_file = secret_path / "admin.token"

    if not token_file.exists():
        return {"status": "error", "message": "Token file not found."}

    with open(token_file, "r") as f:
        expected_token = f.read().strip()

    if request.client.host not in ["127.0.0.1", "::1"]:
        return {"status": "error", "message": "Remote shutdown not allowed."}

    if token != expected_token:
        return {"status": "error", "message": "Invalid token."}

    print("Internal shutdown request received. Running shutdown tasks...")
    try:
        do_shutdown()
    except Exception as e:
        print(f"Error during internal shutdown: {e}")
        return {"status": "error", "message": str(e)}

    server_state.running = False
    if server_state.uvicorn_server:
        server_state.uvicorn_server.should_exit = True

    return {"status": "ok", "message": "Shutdown tasks completed."}


def setup_static_files():
    """Mount the static files directory (uses game folder's web/static if available)."""
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        print(f"Serving static files from: {static_dir}")
    else:
        print(f"Warning: Static directory not found: {static_dir}")


def start_server():
    """Start the atheriz server."""
    setup_game_folder()
    print(f"Starting {settings.SERVERNAME} server...")

    import os

    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"

    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"Server is already running with PID: {old_pid}")
            return
        except (ValueError, ProcessLookupError, FileNotFoundError, OSError):
            print("Removing stale PID file.")
            pid_file.unlink(missing_ok=True)

    try:
        do_startup()
    except Exception as e:
        print(f"Startup tasks failed: {traceback.format_exc()}")
        return

    pid = os.getpid()
    if not save_path.exists():
        save_path.mkdir(parents=True)
        save_path.mkdir(parents=True)

    pid_file = save_path / "server.pid"
    with open(pid_file, "w") as f:
        f.write(str(pid))

    # write admin token
    token = secrets.token_hex(32)
    secret_path = Path(settings.SECRET_PATH)
    if not secret_path.exists():
        secret_path.mkdir(parents=True)

    token_file = secret_path / "admin.token"
    with open(token_file, "w") as f:
        f.write(token)
    # secure permission (read/write for owner only)
    token_file.chmod(0o600)

    if settings.WEBSERVER_ENABLED:
        setup_static_files()

    server_state.running = True
    host = settings.WEBSERVER_INTERFACE
    port = settings.WEBSERVER_PORT

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=settings.LOG_LEVEL,
        ws_ping_interval=20,
        ws_ping_timeout=300,
        timeout_graceful_shutdown=5,
    )

    server_state.uvicorn_server = uvicorn.Server(config)

    print(f"Web server listening on http://{host}:{port}")
    if settings.WEBSOCKET_ENABLED:
        print(f"WebSocket server available at ws://{host}:{port}/ws")

    # handle shutdown signals
    def signal_handler(signum, frame):
        print("\nShutdown signal received...")
        server_state.running = False
        if server_state.uvicorn_server:
            server_state.uvicorn_server.should_exit = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # run the server
    try:
        server_state.uvicorn_server.run()
    finally:
        try:
            do_shutdown()
        except Exception:
            get_database().close()
        print("Server stopped.")
        if pid_file.exists():
            pid_file.unlink()

        secret_path = Path(settings.SECRET_PATH)
        token_file = secret_path / "admin.token"
        if token_file.exists():
            token_file.unlink()


def request_internal_shutdown(port: int | None = None) -> bool:
    """
    Attempt to trigger a graceful shutdown via the internal API.
    Returns True if successful, False otherwise.
    """
    import urllib.request
    import urllib.error
    import json

    port = port or settings.WEBSERVER_PORT
    secret_path = Path(settings.SECRET_PATH)
    token_file = secret_path / "admin.token"

    if not token_file.exists():
        return False

    try:
        with open(token_file, "r") as f:
            token = f.read().strip()
    except Exception:
        return False

    url = f"http://localhost:{port}/_internal/shutdown"
    print(f"Requesting graceful shutdown via internal API...")

    req = urllib.request.Request(url, method="POST")
    req.add_header("X-Admin-Token", token)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                print(f"Internal shutdown response: {data}")
                if data.get("status") == "ok":
                    print("Server has completed shutdown tasks.")
                    return True
    except (urllib.error.URLError, Exception):
        pass

    print("Could not contact server for graceful shutdown (server might be hung or stopped).")
    return False


def stop_server(port: int | None = None):
    """Stop the atheriz server using the PID file."""
    import os
    import psutil

    # try graceful shutdown first
    request_internal_shutdown(port)

    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"

    pid = None

    # try reading PID from file
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
        except ValueError:
            print("Invalid PID file content.")

    # if we have a PID, try to kill it
    if pid:
        try:
            proc = psutil.Process(pid)
            print(f"Stopping server process with PID: {pid}...", end="", flush=True)
            proc.terminate()

            # wait for process to stop
            try:
                proc.wait(timeout=10)
            except psutil.TimeoutExpired:
                print(" Timeout! Force killing...", end="", flush=True)
                proc.kill()
                proc.wait(timeout=5)

            print(" Done.")

            # clean up PID file if the process is gone
            if pid_file.exists():
                if not proc.is_running():
                    pid_file.unlink()
                else:
                    print("\nWarning: Process still exists after kill.")
            return
        except psutil.NoSuchProcess:
            print("\nProcess from PID file not found.")
        except psutil.AccessDenied:
            print(f"\nAccess denied when trying to stop PID {pid}.")
        except Exception as e:
            print(f"\nError stopping server by PID: {e}")

    # fallback: scan for process listening on the port
    target_port = port or settings.WEBSERVER_PORT
    print(f"Scanning for process listening on port {target_port}...")
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == target_port and conn.pid:
                try:
                    proc = psutil.Process(conn.pid)
                    print(
                        f"Found process {proc.name()} (PID: {proc.pid}) listening on port {target_port}...",
                        end="",
                        flush=True,
                    )
                    proc.terminate()

                    # wait for process to stop
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        print("\nProcess did not stop in time. Killing...", end="")
                        proc.kill()
                        proc.wait()

                    print(" Done.")
                    return
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        print("No server process found.")
    except Exception as e:
        print(f"Error scanning for process: {e}")

    if pid_file.exists():
        print("Cleaning up stale PID file.")
        pid_file.unlink()


def main():
    parser = argparse.ArgumentParser(description="AtheriZ - Text-based multiplayer game server")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    start_parser = subparsers.add_parser("start", help="Start the AtheriZ server")
    start_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override the webserver port (default: {settings.WEBSERVER_PORT})",
    )
    start_parser.add_argument(
        "--host", type=str, default=None, help="Override the host interface to bind to"
    )
    start_parser.add_argument(
        "--foreground", "-f", action="store_true", help="Run the server in the foreground"
    )

    restart_parser = subparsers.add_parser("restart", help="Restart the AtheriZ server")
    restart_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override the webserver port (default: {settings.WEBSERVER_PORT})",
    )
    restart_parser.add_argument(
        "--host", type=str, default=None, help="Override the host interface to bind to"
    )
    restart_parser.add_argument(
        "--foreground", "-f", action="store_true", help="Run the server in the foreground"
    )

    stop_parser = subparsers.add_parser("stop", help="Stop the AtheriZ server")
    stop_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override default port (default: {settings.WEBSERVER_PORT})",
    )

    reload_parser = subparsers.add_parser("reload", help="Hot reload game logic")
    reload_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override default port (default: {settings.WEBSERVER_PORT})",
    )

    reset_parser = subparsers.add_parser("reset", help="Delete all game data and start fresh")
    reset_parser.add_argument("-f", "--force", action="store_true", help="Skip confirmation prompt")

    create_parser = subparsers.add_parser("create", help="Create a new account and character")
    create_parser.add_argument("accountname", help="Name of the account")
    create_parser.add_argument("charactername", help="Name of the character")
    create_parser.add_argument("password", help="Password for the account")

    new_parser = subparsers.add_parser("new", help="Create a new game folder with template classes")
    new_parser.add_argument("foldername", help="Name of the folder to create")
    new_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override the webserver port (default: {settings.WEBSERVER_PORT})",
    )
    new_parser.add_argument(
        "--host", type=str, default=None, help="Override the host interface to bind to"
    )
    new_parser.add_argument(
        "--foreground", "-f", action="store_true", help="Run the server in the foreground"
    )

    args = parser.parse_args()

    if args.command == "start":
        if args.port:
            settings.WEBSERVER_PORT = args.port
        if args.host:
            settings.WEBSERVER_INTERFACE = args.host

        if args.foreground:
            start_server()
        else:
            spawn_daemon(args)
    elif args.command == "restart":
        t0 = time.time()

        # override settings if args provided (for port/host)
        if args.port:
            settings.WEBSERVER_PORT = args.port
        if args.host:
            settings.WEBSERVER_INTERFACE = args.host

        import os

        save_path = Path(settings.SAVE_PATH)
        pid_file = save_path / "server.pid"
        old_pid = None
        if pid_file.exists():
            try:
                with open(pid_file, "r") as f:
                    old_pid = int(f.read().strip())
            except ValueError:
                pass

        stop_server(port=args.port)

        if old_pid:
            print(f"Waiting for server (PID {old_pid}) to stop...", end="", flush=True)
            for _ in range(50):
                try:
                    os.kill(old_pid, 0)
                    time.sleep(0.1)
                    print(".", end="", flush=True)
                except (ProcessLookupError, OSError):
                    break
            print(" Done.")

        try:
            setup_game_folder()
            do_startup()
        except Exception as e:
            print(f"Startup tasks failed: {traceback.format_exc()}")
            return

        if args.foreground:
            start_server()
        else:
            spawn_daemon(args)
            print(f"Restart took {(time.time() - t0) * 1000:.2f}ms")
    elif args.command == "stop":
        stop_server(port=args.port)
    elif args.command == "create":
        create_game_data(args)
    elif args.command == "reload":
        do_reload_command(args)
    elif args.command == "reset":
        do_reset_command(args)
    elif args.command == "new":
        import os
        from atheriz.new import create_game_folder
        create_game_folder(args.foldername)
        
        print(f"\nChanging directory to '{args.foldername}'...")
        os.chdir(args.foldername)
        
        if args.port:
            settings.WEBSERVER_PORT = args.port
        if args.host:
            settings.WEBSERVER_INTERFACE = args.host
            
        print("Starting server...")
        if args.foreground:
            start_server()
        else:
            spawn_daemon(args)
    else:
        parser.print_help()


def spawn_daemon(args):
    """Spawn the server in a separate process."""
    import sys
    import subprocess
    import os

    # check if running
    setup_game_folder()
    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"
    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"Server is already running with PID: {old_pid}")
            return
        except (ValueError, ProcessLookupError, FileNotFoundError, OSError):
            pid_file.unlink(missing_ok=True)

    cmd = [sys.executable, "-m", "atheriz.atheriz", "start", "--foreground"]
    if args.port:
        cmd.extend(["--port", str(args.port)])

    if args.host:
        cmd.extend(["--host", str(args.host)])

    save_path = Path(settings.SAVE_PATH)
    if not save_path.exists():
        save_path.mkdir(parents=True)
    log_file = save_path / "server.log"

    print(f"Spawning server in background. Logging to: {log_file}")

    # platform specific flags
    kwargs = {}
    if sys.platform == "win32":
        # DETACHED_PROCESS = 0x00000008
        # CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # separate process group
        kwargs["start_new_session"] = True

    # open log file for append
    with open(log_file, "a") as f:
        # spawn process
        proc = subprocess.Popen(cmd, stdout=f, stderr=f, **kwargs)

    print(f"Server started with PID: {proc.pid}")

    host = args.host or settings.WEBSERVER_INTERFACE
    port = args.port or settings.WEBSERVER_PORT
    if host == "0.0.0.0":
        print(f"Web server running on http://localhost:{port}")
    else:
        print(f"Web server running on http://{host}:{port}")


def create_game_data(args):
    """Create a new account and character."""
    print("Loading existing data...")

    save_path = Path(settings.SAVE_PATH)
    if not save_path.exists():
        save_path.mkdir(parents=True)

    load_objects()

    result: list[Account] = filter_by(lambda x: x.is_account)
    if result:
        for r in result:
            if r.name == args.accountname:
                if not r.check_password(args.password):
                    print(
                        f"Account '{args.accountname}' already exists with a different password..."
                    )
                    return
                if len(r.characters) >= settings.MAX_CHARACTERS:
                    print(
                        f"Account '{args.accountname}' already has {settings.MAX_CHARACTERS} characters..."
                    )
                    return
                character = Object.create(None, args.charactername, is_pc=True)
                r.add_character(character)
                r.at_post_create_character(character)
                add_object(character)
                save_objects()
                print("Success! Character created.")
                return

    print(f"Creating account '{args.accountname}'...")
    account = Account.create(args.accountname, args.password)
    if not account:
        print(f"Account '{args.accountname}' already exists.")
        return
    print(f"Creating character '{args.charactername}'...")
    character = Object.create(None, args.charactername, is_pc=True)
    account.add_character(character)
    add_object(account)
    add_object(character)
    save_objects()
    print("Success! Account and character created.")


def do_reload_command(args):
    """Execute the reload command by calling the internal API."""
    import urllib.request
    import urllib.error
    import json

    port = args.port or settings.WEBSERVER_PORT
    secret_path = Path(settings.SECRET_PATH)
    token_file = secret_path / "admin.token"

    if not token_file.exists():
        print("Error: admin.token not found. Is the server running?")
        return

    with open(token_file, "r") as f:
        token = f.read().strip()

    url = f"http://localhost:{port}/_internal/hot_reload"
    print(f"Triggering hot reload at {url}...")

    t0 = time.time()
    req = urllib.request.Request(url, method="POST")
    req.add_header("X-Admin-Token", token)
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                elapsed = time.time() - t0
                if data.get("status") == "ok":
                    print(f"Success! {data.get('message')}")
                    print(f"Reload took {elapsed * 1000:.2f}ms")
                else:
                    print(f"Failed: {data.get('message')}")
            else:
                print(f"Failed with HTTP {response.status}: {response.read().decode()}")
    except urllib.error.URLError as e:
        print(f"Error connecting to server: {e}")


def do_reset_command(args):
    """Delete all game data and start fresh."""
    import os

    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"

    if pid_file.exists():
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            print("Error: Server is running. Please stop the server before resetting.")
            return
        except (ValueError, ProcessLookupError, FileNotFoundError):
            pass

    if not args.force:
        print("WARNING: This will delete ALL game data. This action cannot be undone.")
        response = input("Are you sure you want to continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return

    print("Deleting game data...")
    if save_path.exists():
        shutil.rmtree(save_path)

    save_path.mkdir(parents=True)

    print("Setting up new world...")
    
    # Try to use local initial_setup.py if it exists
    import sys
    sys.path.insert(0, os.getcwd())
    try:
        import initial_setup as local_setup
        import importlib
        importlib.reload(local_setup) # Ensure we get the latest
        local_setup.do_setup()
        print("  - Used local initial_setup.py")
    except ImportError:
        print("  - local initial_setup.py not found, using default.")
        initial_setup.do_setup()
    
    print("Success! New world created.")

    if not hasattr(args, "port"):
        args.port = None
    if not hasattr(args, "host"):
        args.host = None

    spawn_daemon(args)


if __name__ == "__main__":
    main()
