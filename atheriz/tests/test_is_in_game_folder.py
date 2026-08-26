import os
from pathlib import Path
import pytest


@pytest.fixture
def temp_cwd(tmp_path):
    """Fixture to change CWD to a temp directory and back."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


def test_returns_true_with_settings_and_init_only(temp_cwd):
    """Game folder is detected with just settings.py + __init__.py (no save/ required)."""
    (temp_cwd / "settings.py").write_text("# settings")
    (temp_cwd / "__init__.py").write_text("")

    from atheriz.utils import is_in_game_folder

    assert is_in_game_folder() is True


def test_returns_false_when_settings_missing(temp_cwd):
    from atheriz.utils import is_in_game_folder

    (temp_cwd / "__init__.py").write_text("")

    assert is_in_game_folder() is False


def test_returns_false_when_init_missing(temp_cwd):
    from atheriz.utils import is_in_game_folder

    (temp_cwd / "settings.py").write_text("# settings")

    assert is_in_game_folder() is False


def test_returns_false_when_atheriz_py_present(temp_cwd):
    """The core atheriz package dir contains settings.py + __init__.py + atheriz.py; not a game folder."""
    from atheriz.utils import is_in_game_folder

    (temp_cwd / "settings.py").write_text("# settings")
    (temp_cwd / "__init__.py").write_text("")
    (temp_cwd / "atheriz.py").write_text("# core module")

    assert is_in_game_folder() is False


def test_returns_true_without_save_dir(temp_cwd):
    """Regression: a fresh clone has no save/ (it's gitignored); detection must still succeed."""
    (temp_cwd / "settings.py").write_text("# settings")
    (temp_cwd / "__init__.py").write_text("")

    assert not (temp_cwd / "save").exists()

    from atheriz.utils import is_in_game_folder

    assert is_in_game_folder() is True


def test_is_in_game_folder_windows_branch(temp_cwd, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    (temp_cwd / "settings.py").write_text("# settings")
    (temp_cwd / "__init__.py").write_text("")
    from atheriz.utils import is_in_game_folder

    assert is_in_game_folder() is True
    (temp_cwd / "atheriz.py").write_text("# core")
    assert is_in_game_folder() is False
    monkeypatch.setattr(os, "name", "posix")
    (temp_cwd / "atheriz.py").unlink()
    assert is_in_game_folder() is True


def test_is_in_game_folder_nt_case_insensitive(temp_cwd, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    (temp_cwd / "SETTINGS.PY").write_text("# settings")
    (temp_cwd / "__INIT__.PY").write_text("")
    from atheriz.utils import is_in_game_folder
    import pathlib
    assert is_in_game_folder() is True, "NT filesystem is case-insensitive, detection must be case-insensitive"
    (temp_cwd / "SETTINGS.PY").unlink()
    (temp_cwd / "__INIT__.PY").unlink()
    monkeypatch.setattr(os, "name", "posix")
    (temp_cwd / "settings.py").write_text("# settings")
    (temp_cwd / "__init__.py").write_text("")
    assert is_in_game_folder() is True

def test_is_in_game_folder_nt_mixed_case(temp_cwd, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    (temp_cwd / "Settings.py").write_text("#")
    (temp_cwd / "__init__.py").write_text("")
    from atheriz.utils import is_in_game_folder
    assert is_in_game_folder() is True, "Windows case-insensitive check must handle mixed case"
    (temp_cwd / "Settings.py").unlink()
    monkeypatch.setattr(os, "name", "posix")
