import asyncio
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
import warnings

import pytest

warnings.filterwarnings(
    "ignore",
    message=r".*deallocator.*BaseEventLoop.__del__.*",
    category=pytest.PytestUnraisableExceptionWarning,
)

from atheriz import settings, database_setup
from atheriz.globals import objects as obj_singleton
from atheriz.globals import get as get_singleton
from atheriz.globals import startstop as startstop_module
from atheriz.globals import salt as salt_module


def _ctest_log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S", time.localtime())
    # also monotonic delta for ordering
    mono = f"{time.monotonic():.2f}"
    print(f"[{ts} {mono} conftest] {msg}", file=sys.stderr, flush=True)


def _dump_threads(prefix: str = "") -> None:
    out = [prefix] if prefix else []
    for tid, frame in sys._current_frames().items():
        th = next((t for t in threading.enumerate() if t.ident == tid), None)
        name = th.name if th else f"tid={tid}"
        out.append(f"--- Thread {name} ({tid}) ---")
        out.append("".join(traceback.format_stack(frame)))
    msg = "\n".join(out)
    print(msg, file=sys.stderr, flush=True)
    return msg


def _clear_ticker():
    """Stop and drop the global AsyncTicker so background at_tick coros from a
    prior test can't fire across the test boundary (free-threading safe)."""
    try:
        ticker = get_singleton._ASYNC_TICKER
        if ticker is not None:
            try:
                if ticker.lock.acquire(timeout=1):
                    try:
                        ticker.clear()
                    finally:
                        ticker.lock.release()
                else:
                    try:
                        ticker.clear()
                    except Exception:
                        pass
            except Exception:
                try:
                    ticker.clear()
                except Exception:
                    pass
    except Exception:
        pass
    get_singleton._ASYNC_TICKER = None


def _clear_all_objects_nonblocking():
    try:
        if obj_singleton._ALL_OBJECTS_LOCK.acquire(timeout=1):
            try:
                obj_singleton._ALL_OBJECTS.clear()
            finally:
                obj_singleton._ALL_OBJECTS_LOCK.release()
        else:
            obj_singleton._ALL_OBJECTS.clear()
    except Exception:
        try:
            obj_singleton._ALL_OBJECTS.clear()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def global_test_env(request):
    # Logging: identify which test is running; request.node is available for function-scoped fixtures
    try:
        nodeid = request.node.nodeid
    except Exception:
        nodeid = "unknown"
    _ctest_log(f"ENTER {nodeid}")
    _t0 = time.monotonic()
    # Setup: Redirect SAVE_PATH to a temporary directory
    old_save_path = settings.SAVE_PATH
    old_salt = salt_module._SALT
    temp_dir = tempfile.mkdtemp()
    settings.SAVE_PATH = temp_dir
    if salt_module._SALT is None:
        salt_module._SALT = "testsalt"

    # Ensure database singleton is fresh
    if database_setup._DATABASE:
        try:
            database_setup._DATABASE.close()
        except Exception:
            pass
    database_setup._DATABASE = None
    database_setup._CLOSED = False
    database_setup.do_setup()


    # Clear other globals/state if necessary
    _clear_all_objects_nonblocking()
    try:
        if obj_singleton.TEMP_BANNED_LOCK.acquire(timeout=1):
            try:
                obj_singleton.TEMP_BANNED_IPS.clear()
            finally:
                obj_singleton.TEMP_BANNED_LOCK.release()
        else:
            obj_singleton.TEMP_BANNED_IPS.clear()
    except Exception:
        try:
            obj_singleton.TEMP_BANNED_IPS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.CREATION_COOLDOWN_LOCK.acquire(timeout=1):
            try:
                obj_singleton.CREATION_COOLDOWNS.clear()
            finally:
                obj_singleton.CREATION_COOLDOWN_LOCK.release()
        else:
            obj_singleton.CREATION_COOLDOWNS.clear()
    except Exception:
        try:
            obj_singleton.CREATION_COOLDOWNS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.acquire(timeout=1):
            try:
                obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
            finally:
                obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.release()
        else:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
    except AttributeError:
        pass
    except Exception:
        try:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
        except Exception:
            pass

    # Reset internal ID counter to ensure predictable test IDs if needed
    get_singleton.set_id(-1)

    # Reset other globals if they exist
    get_singleton._NODE_HANDLER = None
    get_singleton._MAP_HANDLER = None
    get_singleton._GAME_TIME = None
    get_singleton._SERVER_CHANNEL = None
    get_singleton._LOGGEDIN_CMDSET = None
    get_singleton._UNLOGGEDIN_CMDSET = None
    get_singleton._CONNECTION_MANAGER = None
    try:
        import atheriz.connection_screen as _cs

        with _cs._LOCK:
            _cs._CACHE = (0, 0, 0)
    except Exception:
        pass

    # Stop any background ticker left running by a previous test, then drop the
    # singleton, so its at_tick coros can't fire across the test boundary.
    _clear_ticker()

    # Reset the shutdown-guard flag so each test gets a fresh shutdown cycle.
    startstop_module._shutdown_completed = False
    try:
        from atheriz.atheriz import server_state
        server_state.running = False
        server_state.uvicorn_server = None
    except Exception:
        pass
    try:
        get_singleton._ASYNC_THREAD_POOL = None
        get_singleton._ASYNC_TICKER = None
        get_singleton._CONNECTION_MANAGER = None
    except Exception:
        pass

    # watchdog: if test doesn't finish in 25s, dump threads (hang diagnosis)
    _watchdog_stop = threading.Event()

    def _watchdog():
        if not _watchdog_stop.wait(25):
            _ctest_log(f"WATCHDOG: {nodeid} still running after 25s (hang?)")
            _dump_threads(f"WATCHDOG {nodeid}")

    _wd_thread = threading.Thread(target=_watchdog, daemon=True, name=f"wd-{nodeid[:30]}")
    _wd_thread.start()
    _ctest_log(f"YIELD {nodeid} setup done in {time.monotonic()-_t0:.2f}s -> running test")
    try:
        yield temp_dir
    finally:
        _watchdog_stop.set()
    _ctest_log(f"TEARDOWN start {nodeid} after {time.monotonic()-_t0:.2f}s")
    _t1 = time.monotonic()

    # Teardown: stop the ticker BEFORE closing the DB so no at_tick runs mid-close.
    _clear_ticker()
    if database_setup._DATABASE:
        try:
            _ctest_log(f"DB close start {nodeid}")
            # Database.close() is internally synchronized via _INIT_LOCK+self.lock;
            # do not hold db.lock externally (would leak if _DATABASE cleared inside close).
            database_setup._DATABASE.close()
            _ctest_log(f"DB close done {nodeid} in {time.monotonic()-_t1:.2f}s")
        except Exception as e:
            _ctest_log(f"DB close failed {nodeid}: {e}\n{traceback.format_exc()}")
    database_setup._DATABASE = None
    database_setup._CLOSED = False

    try:
        shutil.rmtree(temp_dir)
    except OSError as e:
        _ctest_log(f"rmtree failed {nodeid}: {e}")
    _ctest_log(f"rmtree done {nodeid}")

    settings.SAVE_PATH = old_save_path
    salt_module._SALT = old_salt
    _clear_all_objects_nonblocking()
    try:
        if obj_singleton.TEMP_BANNED_LOCK.acquire(timeout=1):
            try:
                obj_singleton.TEMP_BANNED_IPS.clear()
            finally:
                obj_singleton.TEMP_BANNED_LOCK.release()
        else:
            obj_singleton.TEMP_BANNED_IPS.clear()
    except Exception:
        try:
            obj_singleton.TEMP_BANNED_IPS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.CREATION_COOLDOWN_LOCK.acquire(timeout=1):
            try:
                obj_singleton.CREATION_COOLDOWNS.clear()
            finally:
                obj_singleton.CREATION_COOLDOWN_LOCK.release()
        else:
            obj_singleton.CREATION_COOLDOWNS.clear()
    except Exception:
        try:
            obj_singleton.CREATION_COOLDOWNS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.acquire(timeout=1):
            try:
                obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
            finally:
                obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.release()
        else:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
    except AttributeError:
        pass
    except Exception:
        try:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
        except Exception:
            pass
    try:
        import atheriz.connection_screen as _cs2

        with _cs2._LOCK:
            _cs2._CACHE = (0, 0, 0)
    except Exception:
        pass
    try:
        from atheriz.atheriz import server_state
        server_state.running = False
        server_state.uvicorn_server = None
    except Exception:
        pass
    try:
        get_singleton._ASYNC_THREAD_POOL = None
        get_singleton._ASYNC_TICKER = None
        get_singleton._CONNECTION_MANAGER = None
        startstop_module._shutdown_completed = False
    except Exception:
        pass
    _ctest_log(f"LEAVE {nodeid} total {time.monotonic()-_t0:.2f}s")


@pytest.fixture(autouse=True)
def reset_autosave():
    """Ensure the autosave state flag does not leak between tests."""
    from atheriz.globals import autosave

    autosave._autosave_started = False
    yield
    autosave._autosave_started = False


@pytest.fixture(autouse=True)
def reset_connection_manager():
    """Clear the global ConnectionManager singletons between tests."""
    from atheriz import network

    cm = getattr(network, "connection_manager", None)
    if cm is not None:
        try:
            if cm._lock.acquire(timeout=1):
                try:
                    cm._connections.clear()
                    cm._message_handlers.clear()
                    cm._connection_counter = 0
                finally:
                    cm._lock.release()
            else:
                cm._connections.clear()
        except Exception:
            try:
                cm._connections.clear()
            except Exception:
                pass
    get_singleton._CONNECTION_MANAGER = None
    yield
    if cm is not None:
        try:
            if cm._lock.acquire(timeout=1):
                try:
                    cm._connections.clear()
                    cm._message_handlers.clear()
                    cm._connection_counter = 0
                finally:
                    cm._lock.release()
            else:
                cm._connections.clear()
        except Exception:
            try:
                cm._connections.clear()
            except Exception:
                pass
    get_singleton._CONNECTION_MANAGER = None


@pytest.fixture(autouse=True)
def reset_banned_ips():
    """Clear the temporary ban list and creation cooldowns between tests."""
    try:
        if obj_singleton.TEMP_BANNED_LOCK.acquire(timeout=1):
            try:
                obj_singleton.TEMP_BANNED_IPS.clear()
            finally:
                obj_singleton.TEMP_BANNED_LOCK.release()
        else:
            obj_singleton.TEMP_BANNED_IPS.clear()
    except Exception:
        try:
            obj_singleton.TEMP_BANNED_IPS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.CREATION_COOLDOWN_LOCK.acquire(timeout=1):
            try:
                obj_singleton.CREATION_COOLDOWNS.clear()
            finally:
                obj_singleton.CREATION_COOLDOWN_LOCK.release()
        else:
            obj_singleton.CREATION_COOLDOWNS.clear()
    except Exception:
        try:
            obj_singleton.CREATION_COOLDOWNS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.acquire(timeout=1):
            try:
                obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
            finally:
                obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.release()
        else:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
    except AttributeError:
        pass
    except Exception:
        try:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
        except Exception:
            pass
    yield
    try:
        if obj_singleton.TEMP_BANNED_LOCK.acquire(timeout=1):
            try:
                obj_singleton.TEMP_BANNED_IPS.clear()
            finally:
                obj_singleton.TEMP_BANNED_LOCK.release()
        else:
            obj_singleton.TEMP_BANNED_IPS.clear()
    except Exception:
        try:
            obj_singleton.TEMP_BANNED_IPS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.CREATION_COOLDOWN_LOCK.acquire(timeout=1):
            try:
                obj_singleton.CREATION_COOLDOWNS.clear()
            finally:
                obj_singleton.CREATION_COOLDOWN_LOCK.release()
        else:
            obj_singleton.CREATION_COOLDOWNS.clear()
    except Exception:
        try:
            obj_singleton.CREATION_COOLDOWNS.clear()
        except Exception:
            pass
    try:
        if obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.acquire(timeout=1):
            try:
                obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
            finally:
                obj_singleton.FAILED_LOGIN_ATTEMPTS_LOCK.release()
        else:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
    except AttributeError:
        pass
    except Exception:
        try:
            obj_singleton.FAILED_LOGIN_ATTEMPTS.clear()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def reset_lag_gate():
    """Ensure BaseCommand.execute monkey-patches do not leak between tests."""
    from atheriz.commands.base_cmd import Command as BaseCommand

    orig_execute = BaseCommand.execute
    yield
    try:
        if BaseCommand.execute is not orig_execute:
            BaseCommand.execute = orig_execute
    except Exception:
        pass


@pytest.fixture
def fixed_salt(monkeypatch):
    """Pin atheriz.globals.salt._SALT to a known value for deterministic hashes."""
    from atheriz.globals import salt

    monkeypatch.setattr(salt, "_SALT", "testsalt")
    return "testsalt"


@pytest.fixture
def running_loop():
    """Provide a long-lived asyncio loop running on a background thread.

    Yields (loop, submit). `submit(coro)` schedules the coroutine on the
    running loop and returns the concurrent.futures.Future. Mirrors
    test_menu.py's pattern.
    """
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        yield loop
    finally:
        try:
            loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:
            pass
        t.join(timeout=2)
        loop.close()


@pytest.fixture
def fake_connection_factory():
    """Factory: returns a FakeConnection. See atheriz.tests.fakes for details."""
    from atheriz.tests.fakes import FakeConnection

    def _make(session_id="test_conn", **kwargs):
        return FakeConnection(session_id=session_id, **kwargs)

    return _make


@pytest.fixture
def fake_session_factory():
    """Factory: returns a FakeSession. See atheriz.tests.fakes for details."""
    from atheriz.tests.fakes import FakeSession

    def _make(**kwargs):
        return FakeSession(**kwargs)

    return _make


@pytest.fixture
def capture_atheriz_log(tmp_path):
    """Context-manager style fixture: attach a FileHandler to atheriz.logger.

    Yields a `read()` callable that flushes the handler and returns the
    accumulated log content. The handler is removed in teardown.
    """
    from atheriz.logger import logger

    log_file = tmp_path / "atheriz.log"
    file_handler = logging.FileHandler(log_file)
    formatter = logging.Formatter("%(levelname)s: %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    try:
        def read():
            file_handler.flush()
            return log_file.read_text()

        yield read
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()


@pytest.fixture
def db_setup(global_test_env):
    """Alias for global_test_env to avoid breaking tests."""
    from atheriz.globals.objects import load_objects

    load_objects()
    return global_test_env


@pytest.fixture
def temp_env(global_test_env):
    """Alias for global_test_env to avoid breaking tests."""
    return global_test_env


@pytest.fixture
def setup_teardown(global_test_env):
    """Alias for global_test_env to avoid breaking tests."""
    return global_test_env
