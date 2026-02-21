import pytest
import shutil
import tempfile
import os
from atheriz import settings, database_setup
from atheriz.singletons import objects as obj_singleton
from atheriz.singletons import get as get_singleton

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

    
    # Clear other singletons/state if necessary
    obj_singleton._ALL_OBJECTS.clear()
    
    # Reset internal ID counter to ensure predictable test IDs if needed
    get_singleton.set_id(-1)
    
    # Reset other singletons if they exist
    get_singleton._NODE_HANDLER = None
    get_singleton._MAP_HANDLER = None
    get_singleton._GAME_TIME = None
    
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

@pytest.fixture
def db_setup(global_test_env):
    """Alias for global_test_env to avoid breaking tests."""
    from atheriz.singletons.objects import load_objects
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

