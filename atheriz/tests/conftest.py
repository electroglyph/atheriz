import asyncio
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from atheriz import settings, database_setup
from atheriz.globals import objects as obj_singleton
from atheriz.globals import get as get_singleton


@pytest.fixture(autouse=True)
def global_test_env():
    # Setup: Redirect SAVE_PATH to a temporary directory
    old_save_path = settings.SAVE_PATH
    temp_dir = tempfile.mkdtemp()
    settings.SAVE_PATH = temp_dir

    # Ensure database singleton is fresh
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    database_setup._DATABASE = None
    database_setup.do_setup()


    # Clear other globals/state if necessary
    obj_singleton._ALL_OBJECTS.clear()

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

    yield temp_dir

    # Teardown: Clean up
    if database_setup._DATABASE:
        database_setup._DATABASE.close()
    database_setup._DATABASE = None

    try:
        shutil.rmtree(temp_dir)
    except OSError:
        pass

    settings.SAVE_PATH = old_save_path
    obj_singleton._ALL_OBJECTS.clear()


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
    """Clear the temporary ban list between tests."""
    obj_singleton.TEMP_BANNED_IPS.clear()
    yield
    obj_singleton.TEMP_BANNED_IPS.clear()


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
