import os
import shutil
import tempfile
from pathlib import Path
from atheriz.singletons.salt import get_salt
from atheriz import settings
import importlib
import pytest

@pytest.fixture
def temp_cwd(tmp_path):
    """Fixture to change CWD to a temp directory and back."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)

@pytest.fixture
def reset_salt():
    """Fixture to ensure the salt module is fresh before each test."""
    import atheriz.singletons.salt as salt_module
    importlib.reload(salt_module)
    return salt_module

def test_salt_not_created_in_non_game_folder(temp_cwd, reset_salt):
    """Verify salt.txt is not created in a non-game folder."""
    salt = reset_salt.get_salt()
    assert salt is not None
    assert not (temp_cwd / "secret").exists(), "Secret folder should NOT be created in non-game folder"

def test_salt_created_in_game_folder(temp_cwd, reset_salt):
    """Verify salt.txt is created in a game folder."""
    (temp_cwd / "settings.py").write_text("# settings")
    (temp_cwd / "save").mkdir()
    (temp_cwd / "__init__.py").write_text("")
    
    salt = reset_salt.get_salt()
    assert salt is not None
    assert (temp_cwd / "secret" / "salt.txt").exists(), "Secret folder SHOULD be created in game folder"
    
    # Verify persistence
    saved_salt = (temp_cwd / "secret" / "salt.txt").read_text().strip()
    assert salt == saved_salt

def test_salt_created_with_absolute_path(temp_cwd, reset_salt, monkeypatch):
    """Verify salt.txt is created if SECRET_PATH is absolute, even if not in game folder."""
    with tempfile.TemporaryDirectory() as another_temp:
        abs_secret_path = Path(another_temp) / "secret"
        monkeypatch.setattr(settings, "SECRET_PATH", str(abs_secret_path))
        
        salt = reset_salt.get_salt()
        assert salt is not None
        assert (abs_secret_path / "salt.txt").exists(), "Secret folder SHOULD be created with absolute SECRET_PATH"
