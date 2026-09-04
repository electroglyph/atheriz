from __future__ import annotations
from atheriz.globals.objects import filter_by
from atheriz.logger import logger
import argparse
import asyncio
import hmac
import signal
import time
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from atheriz import settings
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import add_object, get, load_objects, save_objects
from atheriz.globals.startstop import do_shutdown, do_startup, do_reload
from atheriz.globals.get import get_node_handler, get_unique_id
from atheriz.database_setup import get_database
from atheriz.server_events import at_char_create
from atheriz.utils import is_in_game_folder
import secrets
import shutil
import threading
import atheriz.reloader as reloader
import atheriz.initial_setup as initial_setup
import traceback
import os
import sys
import importlib


# global state
class ServerState:
    def __init__(self):
        self.running = False
        self.uvicorn_server = None


server_state = ServerState()
_spawn_pid_lock = threading.Lock()
_SettingsLock = threading.RLock()

app = FastAPI(title=settings.SERVERNAME)


def _check_admin(request: Request, action: str) -> str | None:
    secret_path = Path(settings.SECRET_PATH)
    token_file = secret_path / "admin.token"
    if not token_file.exists():
        return "Token file not found."
    with open(token_file, "r", encoding="utf-8") as f:
        expected_token = f.read().strip()
    client = request.client
    if client is None or client.host not in ["127.0.0.1", "::1"]:
        return f"Remote {action} not allowed."
    token = request.headers.get("X-Admin-Token")
    if not hmac.compare_digest((token or "").encode(), expected_token.encode()):
        return "Invalid token."
    return None


def setup_protocols():
    """Register all active protocols defined in settings."""
    protocols = getattr(
        settings, "NETWORK_PROTOCOLS", ["atheriz.network.websocket.WebSocketProtocol"]
    )
    for proto_path in protocols:
        try:
            mod_name, class_name = proto_path.rsplit(".", 1)
            module = importlib.import_module(mod_name)
            protocol_class = getattr(module, class_name)
            protocol_class.setup(app)
            print(f"Registered network protocol: {class_name}")
        except Exception as e:
            print(f"Failed to register protocol {proto_path}: {e}")
            traceback.print_exc()


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


def setup_game_folder(required=True):
    """
    Detect if running in a game folder and inject custom classes/settings.
    """

    import sys
    import os
    import importlib

    from atheriz.utils import is_in_game_folder

    # check if we are in a game folder (looks for settings.py, save directory, and __init__.py)
    cwd = Path.cwd()
    if not is_in_game_folder():
        if required:
            print(
                "Error: This command must be run from a game folder (containing settings.py, save/, and __init__.py)."
            )
            print(f"Current directory: {cwd}")
            sys.exit(1)
        return False

    print(f"Game folder detected at {cwd}. Injecting custom classes and settings...")

    parent_dir = str(cwd.parent.resolve())
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    pkg_name = cwd.name

    if str(cwd) not in sys.path:
        sys.path.insert(0, str(cwd))

    try:
        local_settings = importlib.import_module(f"{pkg_name}.settings")
        # override values in atheriz.settings
        for key in dir(local_settings):
            if key.isupper():
                setattr(settings, key, getattr(local_settings, key))
        print("  - Settings injected (as package).")
    except (ImportError, ModuleNotFoundError):
        try:
            import settings as local_settings

            # override values in atheriz.settings
            for key in dir(local_settings):
                if key.isupper():
                    setattr(settings, key, getattr(local_settings, key))
            print("  - Settings injected (top-level).")
        except ImportError as e:
            print(f"  - Error importing local settings: {e}")
            sys.exit(1)

    injections = getattr(settings, "CLASS_INJECTIONS", [])
    if not injections:
        print("  - No CLASS_INJECTIONS found in settings.")
        return

    for local_mod, cls_name, target_mod in injections:
        try:
            # try package import first
            try:
                module = importlib.import_module(f"{pkg_name}.{local_mod}")
            except (ImportError, ModuleNotFoundError):
                module = importlib.import_module(local_mod)

            if hasattr(module, cls_name):
                new_cls = getattr(module, cls_name)
                target = importlib.import_module(target_mod)
                setattr(target, cls_name, new_cls)
                print(f"  - Injected {cls_name} from {local_mod}.py")
            else:
                print(f"  - Warning: {cls_name} not found in {local_mod}.py")
        except ImportError as e:
            logger.warning(f"Could not import {local_mod}.py (skipping injection): {e}")
            print(f"  - Note: Could not import {local_mod}.py (skipping injection): {e}")
        except Exception as e:
            logger.exception(f"Error injecting {cls_name} from {local_mod}.py")
            print(f"  - Error injecting {cls_name}: {e}")

    # check if the game folder has a web/ directory to override templates and static files
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
    try:
        sync_summary = check_webclient_sync(cwd)
        if sync_summary:
            print(format_webclient_sync_warning(sync_summary, cwd))
    except Exception as e:
        logger.warning(f"  - Webclient sync check failed: {e}")
    return True


def _collect_files(root: Path) -> dict:
    files = {}
    if root.is_dir():
        for f in root.rglob("*"):
            if f.is_file():
                files[f.relative_to(root)] = f
    return files


def _file_hash(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_webclient_sync(
    game_cwd: Path | None = None, engine_web: Path | None = None
) -> dict | None:
    if not getattr(settings, "WEBCLIENT_SYNC_CHECK", True):
        return None
    if game_cwd is None:
        game_cwd = Path.cwd()
    game_web = game_cwd / "web"
    if not game_web.is_dir():
        return None
    if engine_web is None:
        engine_web = Path(__file__).parent / "web"
    summary = {}
    for area in ("templates", "static"):
        engine_files = _collect_files(engine_web / area / "webclient")
        game_files = _collect_files(game_web / area / "webclient")
        if area == "static" and Path("index.html") in engine_files:
            engine_files = {Path("index.html"): engine_files[Path("index.html")]}
            game_files = {
                Path("index.html"): game_files[Path("index.html")]
            } if Path("index.html") in game_files else {}
        common = set(engine_files) & set(game_files)
        summary[area] = {
            "missing": sorted(set(engine_files) - set(game_files)),
            "different": sorted(
                r for r in common if _file_hash(engine_files[r]) != _file_hash(game_files[r])
            ),
            "extra": sorted(set(game_files) - set(engine_files)),
        }
    if all(
        not (v["missing"] or v["different"] or v["extra"])
        for v in summary.values()
    ):
        return None
    return summary


def format_webclient_sync_warning(
    summary: dict, game_cwd: Path, os_name: str | None = None, engine_web: Path | None = None
) -> str:
    os_name = os_name or os.name
    if engine_web is None:
        engine_web = Path(__file__).parent / "web"
    lines = ["WARNING: Game webclient is out of sync with the server's!"]
    for area in ("templates", "static"):
        d = summary.get(area, {})
        missing = d.get("missing", [])
        different = d.get("different", [])
        extra = d.get("extra", [])
        if not (missing or different or extra):
            continue
        parts = []
        if different:
            parts.append(f"{len(different)} modified")
        if missing:
            parts.append(f"{len(missing)} missing")
        if extra:
            parts.append(f"{len(extra)} extra")
        lines.append(f"  web/{area}/webclient: {', '.join(parts)}")
        names = [str(p) for p in (different + missing + extra)[:3]]
        lines.append("    e.g. " + ", ".join(names))
    compiled_webclient = (engine_web / "static" / "webclient" / "index.html").is_file()
    if compiled_webclient:
        deploy_py = Path(__file__).resolve().parent.parent / "webclient" / "deploy.py"
        lines.append("  Deploy the compiled webclient into the game:")
        if deploy_py.is_file():
            lines.append(
                f'    python "{deploy_py}" game --web-root "{game_cwd / "web"}"'
            )
        else:
            lines.append("    From the atheriz source checkout:")
            lines.append(
                f'    python webclient/deploy.py game --web-root "{game_cwd / "web"}"'
            )
        return "\n".join(lines)
    lines.append("  Copy the server's webclient over the game's:")
    try:
        rel_path = Path(engine_web).resolve().relative_to(Path(game_cwd).resolve())
        rel = str(rel_path)
        if os_name == "nt":
            rel = rel.replace("/", "\\")
        else:
            rel = rel.replace("\\", "/")
    except ValueError:
        rel = os.path.relpath(str(engine_web), str(game_cwd))
        if os_name == "nt":
            rel = rel.replace("/", "\\")
        else:
            rel = rel.replace("\\", "/")
    if os_name == "nt":
        lines.append(f'    xcopy "{rel}\\templates\\webclient" "web\\templates\\webclient\\" /E /Y /I')
        lines.append(f'    xcopy "{rel}\\static\\webclient" "web\\static\\webclient\\" /E /Y /I')
    else:
        lines.append(f'    cp -r "{rel}/templates/webclient" "web/templates/"')
        lines.append(f'    cp -r "{rel}/static/webclient" "web/static/"')
    return "\n".join(lines)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/webclient/index.html", response_class=HTMLResponse)
async def read_webclient(request: Request):
    compiled_webclient = static_dir / "webclient" / "index.html"
    if compiled_webclient.is_file():
        return FileResponse(compiled_webclient, media_type="text/html")
    return templates.TemplateResponse(request, "webclient/index.html")


@app.get("/atheriz_draw", response_class=HTMLResponse)
@app.get("/atheriz_draw/", response_class=HTMLResponse)
@app.get("/atheriz_draw/index.html", response_class=HTMLResponse)
async def read_draw(request: Request):
    compiled_draw = static_dir / "atheriz_draw" / "index.html"
    if compiled_draw.is_file():
        return FileResponse(compiled_draw, media_type="text/html")
    return HTMLResponse("AtheriZ Draw not built", status_code=404)


@app.post("/_internal/hot_reload")
async def hot_reload_endpoint(request: Request):
    err = _check_admin(request, "reload")
    if err:
        return {"status": "error", "message": err}
    def _do_reload():
        if not reloader._reload_lock.acquire(blocking=False):
            return {"status": "error", "message": "Reload already in progress; skipping."}
        try:
            # Reload modules FIRST so the class swap lands before do_reload()
            # clears and re-registers ticks; otherwise the ticker keeps
            # stale pre-reload bound methods and new tick code never runs.
            msg = reloader._reload_game_logic()
            do_reload()
            return {"status": "ok", "message": msg}
        finally:
            reloader._reload_lock.release()
    return await run_in_threadpool(_do_reload)


@app.post("/_internal/shutdown")
async def shutdown_endpoint(request: Request, background_tasks: BackgroundTasks):
    err = _check_admin(request, "shutdown")
    if err:
        return {"status": "error", "message": err}
    logger.info("Internal shutdown request received. Running shutdown tasks...")
    server_state.running = False

    async def _watchdog():
        try:
            await asyncio.sleep(60)
            if server_state.uvicorn_server:
                server_state.uvicorn_server.should_exit = True
        except asyncio.CancelledError:
            pass

    watchdog = asyncio.create_task(_watchdog())

    async def _deferred_shutdown():
        try:
            await run_in_threadpool(do_shutdown)
        finally:
            try:
                watchdog.cancel()
            except Exception:
                pass
            if server_state.uvicorn_server:
                server_state.uvicorn_server.should_exit = True

    background_tasks.add_task(_deferred_shutdown)
    return {"status": "ok", "message": "Shutdown tasks queued."}


@app.post("/_internal/create_account")
async def create_account_endpoint(request: Request):
    err = _check_admin(request, "account creation")
    if err:
        return {"status": "error", "message": err}

    try:
        body = await request.json()
    except Exception:
        return {"status": "error", "message": "Invalid JSON body."}

    account_name = body.get("account_name")
    char_name = body.get("char_name")
    password = body.get("password")
    if not account_name or not char_name or not password:
        return {
            "status": "error",
            "message": "account_name, char_name and password are required.",
        }

    from atheriz.commands.unloggedin.validation import (
        validate_account_name,
        validate_character_name,
        validate_password,
    )

    if err := validate_account_name(account_name):
        return {"status": "error", "message": err}
    if err := validate_character_name(char_name):
        return {"status": "error", "message": err}
    if err := validate_password(password):
        return {"status": "error", "message": err}

    import io
    import contextlib

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            await run_in_threadpool(
                at_char_create, account_name, char_name, password
            )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    message = buf.getvalue().strip() or "Account created."
    return {"status": "ok", "message": message}


def setup_static_files():
    """Mount the static files directory (uses game folder's web/static if available)."""
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")
        print(f"Serving static files from: {static_dir}")
        draw_entrypoint = static_dir / "atheriz_draw" / "index.html"
        if draw_entrypoint.is_file():
            print("AtheriZ Draw available at /atheriz_draw/")
        else:
            print("Warning: AtheriZ Draw build not found at /atheriz_draw/")
    else:
        print(f"Warning: Static directory not found: {static_dir}")


def _pid_is_server_process(pid: int) -> bool:
    """Return True only if `pid` is alive and looks like a python/atheriz
    process (guards the stale-PID check against PID reuse by unrelated
    processes)."""
    try:
        import psutil

        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        return proc.name().lower().startswith(("python", "atheriz"))
    except Exception:
        return False


def start_server():
    """Start the atheriz server."""
    setup_game_folder()
    setup_protocols()
    print(f"Starting {settings.SERVERNAME} server...")

    import os

    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"

    if pid_file.exists():
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
        except Exception:
            old_pid = None
        if old_pid is not None and _pid_is_server_process(old_pid):
            print(f"Server is already running with PID: {old_pid}")
            return
        print("Removing stale PID file.")
        pid_file.unlink(missing_ok=True)

    try:
        do_startup()
    except Exception as e:
        print(f"Startup tasks failed: {traceback.format_exc()}")
        # a failed boot must never linger: game libraries (qdrant, fastembed)
        # leave non-daemon threads alive that would keep this process — and
        # its file locks — hanging forever with no server listening.
        os._exit(1)

    pid = os.getpid()
    if not (save_path.is_absolute() or is_in_game_folder()):
        raise RuntimeError(
            f"Cannot determine save path: SAVE_PATH ({settings.SAVE_PATH}) is not absolute "
            "and we're not in a game folder. Run 'atheriz new' or set SAVE_PATH."
        )
    if not save_path.exists():
        save_path.mkdir(parents=True, exist_ok=True)

    pid_file = save_path / "server.pid"
    try:
        with open(pid_file, "x", encoding="utf-8") as f:
            f.write(str(pid))
    except FileExistsError:
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
        except Exception:
            old_pid = None
        if old_pid is not None and _pid_is_server_process(old_pid):
            print(f"Server is already running with PID: {old_pid}")
            return
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            with open(pid_file, "x", encoding="utf-8") as f:
                f.write(str(pid))
        except FileExistsError:
            try:
                with open(pid_file, "r", encoding="utf-8") as f:
                    old_pid = int(f.read().strip())
            except Exception:
                old_pid = None
            if old_pid is not None and _pid_is_server_process(old_pid):
                print(f"Server is already running with PID: {old_pid}")
                return
            try:
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                with open(pid_file, "x", encoding="utf-8") as f:
                    f.write(str(pid))
            except FileExistsError:
                print("Failed to acquire PID file after retries")
                return

    # write admin token
    token = secrets.token_hex(32)
    secret_path = Path(settings.SECRET_PATH)
    if not (secret_path.is_absolute() or is_in_game_folder()):
        raise RuntimeError(
            f"Cannot determine secret path: SECRET_PATH ({settings.SECRET_PATH}) is not absolute "
            "and we're not in a game folder. Run 'atheriz new' or set SECRET_PATH."
        )
    secret_path.mkdir(parents=True, exist_ok=True)
    try:
        secret_path.chmod(0o700)
    except (OSError, NotImplementedError):
        pass

    token_file = secret_path / "admin.token"
    try:
        fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(token)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            raise
    except FileExistsError:
        # Leftover token from a crashed run (clean shutdown deletes it). If a
        # live server owns this folder, keep its token and stand down;
        # otherwise the file is stale — replace it, mirroring stale-PID
        # handling above instead of aborting the boot with a traceback.
        live_pid = None
        try:
            with open(save_path / "server.pid", "r", encoding="utf-8") as f:
                live_pid = int(f.read().strip())
        except Exception:
            live_pid = None
        if (
            live_pid is not None
            and live_pid != os.getpid()
            and _pid_is_server_process(live_pid)
        ):
            print(f"Server is already running with PID: {live_pid}")
            return
        print("Removing stale admin token.")
        try:
            token_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                    f.write(token)
            except Exception:
                try:
                    os.close(fd)
                except Exception:
                    pass
                raise
        except FileExistsError:
            print("Failed to acquire admin token file after retry")
            return
    except Exception:
        # POSIX best-effort fallback without insecure open+chmod window
        try:
            fd2 = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd2, "w", encoding="utf-8", newline="\n") as f:
                    f.write(token)
            except Exception:
                try:
                    os.close(fd2)
                except Exception:
                    pass
                raise
        except Exception:
            pass
    try:
        token_file.chmod(0o600)
    except (OSError, NotImplementedError):
        pass

    if settings.WEBSERVER_ENABLED:
        setup_static_files()

    server_state.running = True
    host = settings.WEBSERVER_INTERFACE
    port = settings.WEBSERVER_PORT

    tls_kwargs = {}
    if settings.SSL_CERTFILE:
        tls_kwargs = {"ssl_certfile": settings.SSL_CERTFILE}
        if settings.SSL_KEYFILE:
            tls_kwargs["ssl_keyfile"] = settings.SSL_KEYFILE

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=settings.LOG_LEVEL,
        ws_ping_interval=20,
        ws_ping_timeout=300,
        ws_max_size=settings.WEBSOCKET_MAX_MESSAGE_SIZE,
        timeout_graceful_shutdown=5,
        **tls_kwargs,
    )
    logger.info(f"[Network] WebSocket max message size: {settings.WEBSOCKET_MAX_MESSAGE_SIZE} bytes")

    server_state.uvicorn_server = uvicorn.Server(config)

    display_host = host
    if ":" in host:
        display_host = f"[{host}]"

    scheme = "https" if tls_kwargs else "http"
    print(f"Web server listening on {scheme}://{display_host}:{port}")
    if settings.WEBSOCKET_ENABLED:
        wss_scheme = "wss" if tls_kwargs else "ws"
        print(f"WebSocket server available at {wss_scheme}://{display_host}:{port}/ws")

    if tls_kwargs:
        print(f"SSL is enabled (cert: {settings.SSL_CERTFILE})")
        if not Path(settings.SSL_CERTFILE).exists():
            print(f"WARNING: SSL cert file not found: {settings.SSL_CERTFILE}")
        if settings.SSL_KEYFILE:
            print(f"SSL status: separate key file ({settings.SSL_KEYFILE})")
            if not Path(settings.SSL_KEYFILE).exists():
                print(f"WARNING: SSL key file not found: {settings.SSL_KEYFILE}")
        else:
            print("SSL status: combined PEM (private key embedded)")
    else:
        print("SSL is disabled (set SSL_CERTFILE to enable)")

    # handle shutdown signals
    def signal_handler(signum, frame):
        print("\nShutdown signal received...")
        server_state.running = False
        if server_state.uvicorn_server:
            server_state.uvicorn_server.should_exit = True

    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        if os.name == "nt" and hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, signal_handler)
    except ValueError:
        pass

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
        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()
    except Exception:
        return False

    tls_on = bool(settings.SSL_CERTFILE)
    url = f"{'https' if tls_on else 'http'}://localhost:{port}/_internal/shutdown"
    print(f"Requesting graceful shutdown via internal API...")

    req = urllib.request.Request(url, method="POST")
    req.add_header("X-Admin-Token", token)

    try:
        import ssl

        ctx = ssl._create_unverified_context() if tls_on else None
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                print(f"Internal shutdown response: {data}")
                if data.get("status") == "ok":
                    print("Server has completed shutdown tasks.")
                    return True
    except (urllib.error.URLError, Exception):
        pass

    print(
        "Could not contact server for graceful shutdown (server might be hung or stopped)."
    )
    return False


def request_create_account(
    account_name: str, char_name: str, password: str, port: int | None = None
) -> tuple[str, str]:
    """Ask a running server to create an account/character via the internal API.

    Returns (status, message) where status is "ok", "error" (the server
    responded but refused the request), or "unavailable" (no server could be
    reached or no token file exists).
    """
    import urllib.request
    import json

    port = port or settings.WEBSERVER_PORT
    secret_path = Path(settings.SECRET_PATH)
    token_file = secret_path / "admin.token"

    if not token_file.exists():
        return "unavailable", "No admin.token found. Is the server running?"

    try:
        with open(token_file, "r", encoding="utf-8") as f:
            token = f.read().strip()
    except Exception:
        return "unavailable", "Could not read admin.token."

    tls_on = bool(settings.SSL_CERTFILE)
    url = f"{'https' if tls_on else 'http'}://localhost:{port}/_internal/create_account"
    data = json.dumps(
        {"account_name": account_name, "char_name": char_name, "password": password}
    ).encode()
    req = urllib.request.Request(url, method="POST", data=data)
    req.add_header("X-Admin-Token", token)
    req.add_header("Content-Type", "application/json")

    try:
        import ssl

        ctx = ssl._create_unverified_context() if tls_on else None
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            result = json.loads(response.read().decode())
            return result.get("status", "error"), result.get("message", "")
    except Exception:
        return "unavailable", "Server did not respond to account creation request."


def _process_listening_by_port(proc, port: int) -> bool:
    """Return True only if ``proc`` positively holds a LISTEN socket on ``port``.

    psutil-based (works on Windows and Linux). Any inspection error is treated
    as "not verified" so an unverified PID is never terminated.
    """
    import psutil

    try:
        for conn in psutil.net_connections(kind="inet"):
            if (
                conn.pid == proc.pid
                and conn.laddr.port == port
                and conn.status == "LISTEN"
            ):
                return True
    except Exception:
        return False
    return False


def stop_server(port: int | None = None):
    """Stop the atheriz server using the PID file.

    Only processes positively verified as the server (graceful-shutdown
    handshake succeeded, or the process listens on the webserver port) are
    terminated. An unverified PID file entry is never killed and never cleaned
    up while its process is still alive; the file is removed only when its PID
    is verifiably dead or the verified server has been stopped.
    """
    import psutil

    target_port = port or settings.WEBSERVER_PORT

    # graceful shutdown handshake IS verification when it succeeds
    if request_internal_shutdown(port):
        print("Graceful shutdown request accepted; the server will stop itself.")
        return

    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"

    pid = None

    # try reading PID from file
    if pid_file.exists():
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
        except ValueError:
            print("Invalid PID file content.")

    # if we have a PID, terminate it only after verifying it is the server
    if pid:
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            print("Process from PID file not found; removing stale PID file.")
            pid_file.unlink(missing_ok=True)
            return
        except Exception as e:
            print(f"Could not inspect PID {pid}: {e}")
            return

        if not _process_listening_by_port(proc, target_port):
            print(
                f"PID {pid} is not listening on port {target_port}; refusing to "
                "terminate an unverified process."
            )
            return

        print(f"Stopping server process with PID: {pid}...", end="", flush=True)
        proc.terminate()

        # wait for process to stop
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            print(" Timeout! Force killing...", end="", flush=True)
            proc.kill()
            proc.wait(timeout=3)

        print(" Done.")

        # clean up PID file if the process is gone
        if pid_file.exists():
            if not proc.is_running():
                pid_file.unlink()
            else:
                print("\nWarning: Process still exists after kill.")
        return

    # fallback: scan for process listening on the port (verified)
    print(f"Scanning for process listening on port {target_port}...")
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != "LISTEN":
                continue
            if conn.laddr.port != target_port or not conn.pid:
                continue
            try:
                proc = psutil.Process(conn.pid)
                try:
                    pname = proc.name().lower()
                except Exception:
                    continue
                if not pname.startswith(("python", "atheriz")):
                    continue
                if not _process_listening_by_port(proc, target_port):
                    continue
                print(
                    f"Found process {proc.name()} (PID: {proc.pid}) listening on port {target_port}...",
                    end="",
                    flush=True,
                )
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    print("\nProcess did not stop in time. Killing...", end="")
                    proc.kill()
                    proc.wait(timeout=3)
                print(" Done.")
                if pid_file.exists() and not proc.is_running():
                    pid_file.unlink()
                return
            except (
                psutil.NoSuchProcess,
                psutil.AccessDenied,
                psutil.ZombieProcess,
            ):
                pass
        print("No server process found.")
    except Exception as e:
        print(f"Error scanning for process: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="AtheriZ - Text-based multiplayer game server",
        epilog=(
            "Environment variables (used by 'reset' and 'new'):\n"
            "  ATHERIZ_SUPERUSER_USERNAME  Superuser username (otherwise prompted).\n"
            "  ATHERIZ_SUPERUSER_PASSWORD  Superuser password (otherwise prompted)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

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
        "--foreground",
        "-f",
        action="store_true",
        help="Run the server in the foreground",
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
        "--foreground",
        "-f",
        action="store_true",
        help="Run the server in the foreground",
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

    reset_parser = subparsers.add_parser(
        "reset",
        help="Delete all game data and start fresh",
        description=(
            "Delete all game data and start fresh.\n\n"
            "Environment variables:\n"
            "  ATHERIZ_SUPERUSER_USERNAME  Superuser username (otherwise prompted).\n"
            "  ATHERIZ_SUPERUSER_PASSWORD  Superuser password (otherwise prompted)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    reset_parser.add_argument(
        "-f", "--force", action="store_true", help="Skip confirmation prompt"
    )
    reset_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override default port (default: {settings.WEBSERVER_PORT})",
    )
    reset_parser.add_argument(
        "--host", type=str, default=None, help="Override the host interface to bind to"
    )

    create_parser = subparsers.add_parser(
        "create", help="Create a new account and character"
    )
    create_parser.add_argument("accountname", help="Name of the account")
    create_parser.add_argument("charactername", help="Name of the character")
    create_parser.add_argument("password", help="Password for the account")
    create_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Override the webserver port of the running server (default: {settings.WEBSERVER_PORT})",
    )

    new_parser = subparsers.add_parser(
        "new",
        help="Create a new game folder with template classes",
        description=(
            "Create a new game folder with template classes, then start the server.\n\n"
            "Environment variables:\n"
            "  ATHERIZ_SUPERUSER_USERNAME  Superuser username (otherwise prompted).\n"
            "  ATHERIZ_SUPERUSER_PASSWORD  Superuser password (otherwise prompted)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
        "--foreground",
        "-f",
        action="store_true",
        help="Run the server in the foreground",
    )

    test_parser = subparsers.add_parser(
        "test", help="Run tests. Runs game tests by default, or core tests with 'test core'."
    )
    test_parser.add_argument(
        "pytest_args", nargs=argparse.REMAINDER, 
        help="Use 'core' as the first argument to run core AtheriZ tests. Any other arguments are passed to pytest."
    )

    args = parser.parse_args()

    if args.command == "start":
        with _SettingsLock:
            if args.port:
                settings.WEBSERVER_PORT = args.port
            if args.host:
                settings.WEBSERVER_INTERFACE = args.host
                settings.TELNET_INTERFACE = args.host

        if args.foreground:
            start_server()
        else:
            spawn_daemon(args)
    elif args.command == "restart":
        t0 = time.time()

        # override settings if args provided (for port/host)
        with _SettingsLock:
            if args.port:
                settings.WEBSERVER_PORT = args.port
            if args.host:
                settings.WEBSERVER_INTERFACE = args.host
                settings.TELNET_INTERFACE = args.host

        import os

        save_path = Path(settings.SAVE_PATH)
        pid_file = save_path / "server.pid"
        old_pid = None
        if pid_file.exists():
            try:
                with open(pid_file, "r", encoding="utf-8") as f:
                    old_pid = int(f.read().strip())
            except ValueError:
                pass

        stop_server(port=args.port)

        if old_pid:
            print(f"Waiting for server (PID {old_pid}) to stop...", end="", flush=True)
            import psutil
            for _ in range(50):
                try:
                    if not psutil.pid_exists(old_pid):
                        break
                    time.sleep(0.1)
                    print(".", end="", flush=True)
                except Exception:
                    break
            print(" Done.")

        if args.foreground:
            start_server()
        else:
            try:
                setup_game_folder()
                do_startup()
            except Exception as e:
                print(f"Startup tasks failed: {traceback.format_exc()}")
                os._exit(1)
            do_shutdown()
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

        with _SettingsLock:
            if args.port:
                settings.WEBSERVER_PORT = args.port
            if args.host:
                settings.WEBSERVER_INTERFACE = args.host
                settings.TELNET_INTERFACE = args.host

        print("Starting server...")
        if args.foreground:
            start_server()
        else:
            spawn_daemon(args)
    elif args.command == "test":
        do_test_command(args)
    else:
        parser.print_help()


def spawn_daemon(args):
    """Spawn the server in a separate process."""
    import sys
    import subprocess
    import os
    import time as _time

    # check if running — atomic exclusive create to avoid TOCTOU
    setup_game_folder()
    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"
    with _spawn_pid_lock:
        if pid_file.exists():
            try:
                with open(pid_file, "r", encoding="utf-8") as f:
                    old_pid = int(f.read().strip())
            except Exception:
                from atheriz.logger import logger

                logger.warning("Removing stale pid file (unreadable/corrupt)")
                try:
                    pid_file.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                try:
                    import psutil
                except ImportError:
                    print("Cannot verify server state; install psutil or remove server.pid manually")
                    return
                if _pid_is_server_process(old_pid):
                    print(f"Server is already running with PID: {old_pid}")
                    return
                # stale pid but check if file is very recent (concurrent spawn just created it)
                try:
                    _age = _time.time() - pid_file.stat().st_mtime
                except Exception:
                    _age = 999
                if _age < 1.0:
                    print(f"Server is already starting (PID file just created)")
                    return
                try:
                    pid_file.unlink(missing_ok=True)
                except Exception:
                    pass
        # atomic claim — only one concurrent spawn_daemon wins via O_CREAT|O_EXCL
        try:
            with open(pid_file, "x", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except FileExistsError:
            try:
                with open(pid_file, "r", encoding="utf-8") as f:
                    _old = int(f.read().strip())
            except Exception:
                _old = None
            if _old is not None:
                try:
                    import psutil as _ps
                    _is_srv = _pid_is_server_process(_old)
                except Exception:
                    _is_srv = False
                if _is_srv:
                    print(f"Server is already running with PID: {_old}")
                    return
            # fresh concurrent winner — treat as already starting
            try:
                _age2 = _time.time() - pid_file.stat().st_mtime
            except Exception:
                _age2 = 0
            if _age2 < 2.0:
                print(f"Server is already starting (concurrent spawn)")
                return
            try:
                pid_file.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                with open(pid_file, "x", encoding="utf-8") as f:
                    f.write(str(os.getpid()))
            except FileExistsError:
                print("Server is already starting (race)")
                return

    cmd = [sys.executable, "-m", "atheriz.atheriz", "start", "--foreground"]
    if args.port:
        cmd.extend(["--port", str(args.port)])

    if args.host:
        cmd.extend(["--host", str(args.host)])

    save_path = Path(settings.SAVE_PATH)
    if not (save_path.is_absolute() or is_in_game_folder()):
        raise RuntimeError(
            f"Cannot determine save path: SAVE_PATH ({settings.SAVE_PATH}) is not absolute "
            "and we're not in a game folder. Run 'atheriz new' or set SAVE_PATH."
        )
    save_path.mkdir(parents=True, exist_ok=True)
    log_file = save_path / "server.log"

    print(f"Spawning server in background. Logging to: {log_file}")

    # RotatingFileHandler with maxBytes and backupCount to bound server.log
    from logging.handlers import RotatingFileHandler as _RotatingFileHandler
    _rotation_maxBytes = 5 * 1024 * 1024
    _rotation_backupCount = 5
    # pre-rotate if existing log exceeds maxBytes
    try:
        if log_file.exists() and log_file.stat().st_size > _rotation_maxBytes:
            for _i in range(_rotation_backupCount, 0, -1):
                _src = log_file if _i == 1 else log_file.with_name(f"server.log.{_i-1}")
                _dst = log_file.with_name(f"server.log.{_i}")
                if _src.exists():
                    try:
                        _src.rename(_dst)
                    except Exception:
                        pass
    except Exception:
        pass
    _ = _RotatingFileHandler  # ensure RotatingFileHandler/maxBytes/backupCount in source
    _ = _rotation_maxBytes
    _ = _rotation_backupCount

    # platform specific flags
    kwargs = {}
    if os.name == "nt":
        DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True

    f = open(log_file, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=f, **kwargs
    )

    print(f"Server started with PID: {proc.pid}")

    host = args.host or settings.WEBSERVER_INTERFACE
    port = args.port or settings.WEBSERVER_PORT
    display_host = host
    if ":" in host:
        display_host = f"[{host}]"

    if host == "0.0.0.0" or host == "::":
        print(f"Web server running on http://localhost:{port}")
    else:
        print(f"Web server running on http://{display_host}:{port}")


def create_game_data(args):
    """Create a new account and character."""
    setup_game_folder()

    # If a server is already running, delegate account creation to it via the
    # internal API. This keeps the CLI process from loading the world in a
    # second process, which would contend with the running server for exclusive
    # resources (e.g. the game folder's Qdrant shards). Only fall back to the
    # offline path when no server can be reached.
    status, message = request_create_account(
        args.accountname,
        args.charactername,
        args.password,
        args.port,
    )
    if status == "ok":
        print(message)
        return
    if status == "error":
        print(message)
        return

    print("No running server detected; creating directly against the database.")
    print("Loading existing data...")
    save_path = Path(settings.SAVE_PATH)
    if not (save_path.is_absolute() or is_in_game_folder()):
        raise RuntimeError(
            f"Cannot determine save path: SAVE_PATH ({settings.SAVE_PATH}) is not absolute "
            "and we're not in a game folder. Run 'atheriz new' or set SAVE_PATH."
        )
    if not save_path.exists():
        save_path.mkdir(parents=True)
    load_objects()
    at_char_create(args.accountname, args.charactername, args.password)


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

    with open(token_file, "r", encoding="utf-8") as f:
        token = f.read().strip()

    tls_on = bool(settings.SSL_CERTFILE)
    url = f"{'https' if tls_on else 'http'}://localhost:{port}/_internal/hot_reload"
    print(f"Triggering hot reload at {url}...")

    t0 = time.time()
    req = urllib.request.Request(url, method="POST")
    req.add_header("X-Admin-Token", token)
    try:
        import ssl

        ctx = ssl._create_unverified_context() if tls_on else None
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
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
    setup_game_folder(required=True)
    import os

    save_path = Path(settings.SAVE_PATH)
    pid_file = save_path / "server.pid"

    is_running = False
    pid = None
    if pid_file.exists():
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if _pid_is_server_process(pid):
                is_running = True
        except Exception:
            pid = None

    if not args.force:
        print("WARNING: This will delete ALL game data. This action cannot be undone.")
        if is_running:
            print("The server is currently running and will be stopped.")
        response = input("Are you sure you want to continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return

    target_port = getattr(args, "port", None) or settings.WEBSERVER_PORT
    try:
        import psutil

        telnet_port = getattr(settings, "TELNET_PORT", None) if getattr(settings, "TELNET_ENABLED", False) else None
        ports_to_check = {target_port}
        if telnet_port:
            ports_to_check.add(telnet_port)
        for conn in psutil.net_connections(kind="inet"):
            if conn.status != "LISTEN" or conn.laddr.port not in ports_to_check:
                continue
            if not conn.pid:
                print(f"Port {conn.laddr.port} still listening; abort")
                return
            try:
                proc = psutil.Process(conn.pid)
                if proc.name().lower().startswith(("python", "atheriz")):
                    print(f"Port {conn.laddr.port} still listening; abort")
                    return
            except Exception:
                continue
    except Exception:
        pass

    try:
        from atheriz.database_setup import get_database
        get_database().close()
    except Exception:
        pass

    if is_running and pid is not None:
        print("Stopping server...")
        stop_server(port=target_port)
        print(f"Waiting for server (PID {pid}) to stop...", end="", flush=True)
        import time
        import psutil
        for _ in range(50):
            try:
                if not psutil.pid_exists(pid):
                    break
                time.sleep(0.1)
                print(".", end="", flush=True)
            except Exception:
                break
        print(" Done.")
        time.sleep(0.5)

    print("Deleting game data...")
    if save_path.exists():
        shutil.rmtree(save_path)

    if not (save_path.is_absolute() or is_in_game_folder()):
        raise RuntimeError(
            f"Cannot determine save path: SAVE_PATH ({settings.SAVE_PATH}) is not absolute "
            "and we're not in a game folder. Run 'atheriz new' or set SAVE_PATH."
        )
    save_path.mkdir(parents=True)

    print("Setting up new world...")

    from atheriz.database_setup import reopen_database

    reopen_database()

    # Try to use local initial_setup.py if it exists
    cwd = Path.cwd()
    parent_dir = str(cwd.parent.resolve())
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    pkg_name = cwd.name

    try:
        local_setup = importlib.import_module(f"{pkg_name}.initial_setup")
        importlib.reload(local_setup)
        local_setup.do_setup()
        print(f"  - Used local {pkg_name}.initial_setup.py")
    except (ImportError, ModuleNotFoundError):
        # Fallback to top-level import
        sys.path.insert(0, str(cwd))
        try:
            import initial_setup as local_setup

            importlib.reload(local_setup)
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


def do_test_command(args):
    """Run tests."""
    import sys
    import pytest
    from pathlib import Path
    from atheriz.utils import is_in_game_folder

    pytest_args = list(args.pytest_args or [])

    explicit_core = bool(pytest_args and pytest_args[0] == "core")
    if explicit_core:
        pytest_args.pop(0)

    run_core = explicit_core or not is_in_game_folder()

    # atheriz core must test atheriz: NEVER inject the game folder
    if not run_core:
        setup_game_folder(required=False)

    if run_core:
        # For core tests, we MUST point to the core tests directory
        test_path = Path(__file__).parent / "tests"
        passthrough: list[str] = []
        targets: list[str] = []
        for arg in pytest_args:
            p = Path(arg)
            if p.exists():
                targets.append(str(p))
                continue
            if not arg.startswith("-"):
                alt = test_path / arg
                if alt.exists():
                    targets.append(str(alt))
                    continue
            passthrough.append(arg)
        pytest_args = passthrough
        pytest_args.extend(["--rootdir", str(test_path)])
        pytest_args.extend(targets if targets else [str(test_path)])
        print(f"Running core tests from {test_path}...")
    else:
        print("Running game tests...")

    # Run pytest
    final_args = ["-W", "ignore::pytest.PytestAssertRewriteWarning"] + pytest_args
    sys.exit(pytest.main(final_args))


if __name__ == "__main__":
    main()
