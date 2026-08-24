import asyncio
import logging
import os
import shutil
import tempfile
import threading
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


def _clear_ticker():
    """Stop and drop the global AsyncTicker so background at_tick coros from a
    prior test can't fire across the test boundary (free-threading safe)."""
    try:
        get_singleton.get_async_ticker().clear()
    except Exception:
        pass
    get_singleton._ASYNC_TICKER = None


@pytest.fixture(autouse=True)
def global_test_env():
    # Setup: Redirect SAVE_PATH to a temporary directory
    old_save_path = settings.SAVE_PATH
    old_salt = salt_module._SALT
    temp_dir = tempfile.mkdtemp()
    settings.SAVE_PATH = temp_dir
    if salt_module._SALT is None:
        salt_module._SALT = "testsalt"

    # Ensure database singleton is fresh
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    database_setup._DATABASE = None
    database_setup._CLOSED = False
    database_setup.do_setup()


    # Clear other globals/state if necessary
    obj_singleton._ALL_OBJECTS.clear()
    with obj_singleton.TEMP_BANNED_LOCK:
        obj_singleton.TEMP_BANNED_IPS.clear()
    with obj_singleton.CREATION_COOLDOWN_LOCK:
        obj_singleton.CREATION_COOLDOWNS.clear()

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

    yield temp_dir

    # Teardown: stop the ticker BEFORE closing the DB so no at_tick runs mid-close.
    _clear_ticker()
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    database_setup._DATABASE = None
    database_setup._CLOSED = False

    try:
        shutil.rmtree(temp_dir)
    except OSError:
        pass

    settings.SAVE_PATH = old_save_path
    salt_module._SALT = old_salt
    obj_singleton._ALL_OBJECTS.clear()
    with obj_singleton.TEMP_BANNED_LOCK:
        obj_singleton.TEMP_BANNED_IPS.clear()
    with obj_singleton.CREATION_COOLDOWN_LOCK:
        obj_singleton.CREATION_COOLDOWNS.clear()
    try:
        import atheriz.connection_screen as _cs2

        with _cs2._LOCK:
            _cs2._CACHE = (0, 0, 0)
    except Exception:
        pass


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
        with cm._lock:
            cm._connections.clear()
            cm._message_handlers.clear()
            cm._connection_counter = 0
    get_singleton._CONNECTION_MANAGER = None
    yield
    if cm is not None:
        with cm._lock:
            cm._connections.clear()
            cm._message_handlers.clear()
            cm._connection_counter = 0
    get_singleton._CONNECTION_MANAGER = None


@pytest.fixture(autouse=True)
def reset_banned_ips():
    """Clear the temporary ban list and creation cooldowns between tests."""
    with obj_singleton.TEMP_BANNED_LOCK:
        obj_singleton.TEMP_BANNED_IPS.clear()
    with obj_singleton.CREATION_COOLDOWN_LOCK:
        obj_singleton.CREATION_COOLDOWNS.clear()
    yield
    with obj_singleton.TEMP_BANNED_LOCK:
        obj_singleton.TEMP_BANNED_IPS.clear()
    with obj_singleton.CREATION_COOLDOWN_LOCK:
        obj_singleton.CREATION_COOLDOWNS.clear()


@pytest.fixture(autouse=True)
def reset_lag_gate():
    """Ensure grotto's lag_gate monkey-patch on BaseCommand does not leak
    between core tests. Full-suite runs may trigger a real hot-reload (via
    reloader) that imports grotto and installs the wrapper; core
    test_base_cmd expects the original BaseCommand.execute (bound method, not
    functools.partial)."""
    from atheriz.commands.base_cmd import Command as BaseCommand

    # Save original before test
    orig_execute = BaseCommand.execute
    orig_flag = getattr(BaseCommand, "_grotto_lag_gated", False)
    yield
    # Restore after test — remove grotto's wrapper if it was installed
    try:
        if getattr(BaseCommand, "_grotto_lag_gated", False) and not orig_flag:
            # grotto installed it during this test; restore original
            BaseCommand.execute = orig_execute
            if hasattr(BaseCommand, "_grotto_lag_gated"):
                delattr(BaseCommand, "_grotto_lag_gated")
        elif BaseCommand.execute is not orig_execute:
            BaseCommand.execute = orig_execute
            if hasattr(BaseCommand, "_grotto_lag_gated"):
                try:
                    delattr(BaseCommand, "_grotto_lag_gated")
                except Exception:
                    pass
    except Exception:
        pass
    # Also purge grotto from sys.modules to keep core isolation (optional)
    # but keep it minimal — only remove grotto.* that were loaded via reload
    # during the test, so next test starts clean. Core tests never need grotto.
    import sys

    for mod in list(sys.modules.keys()):
        if mod == "grotto" or mod.startswith("grotto."):
            # Do not remove if it was already loaded before test suite start
            # (e.g., if running `grotto` game tests, keep it). For core, it
            # should not have been loaded before; safe to purge.
            if mod not in reset_lag_gate._preloaded_grotto:
                sys.modules.pop(mod, None)


# Remember which grotto modules were preloaded before any test (usually none for core)
import sys as _sys_for_grotto
reset_lag_gate._preloaded_grotto = {m for m in _sys_for_grotto.modules if m == "grotto" or m.startswith("grotto.")}


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
