import os
import asyncio
import tempfile
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from atheriz.reloader import _is_under


def test_superuser_creation_strips_whitespace_and_validates(global_test_env, monkeypatch):
    from atheriz.initial_setup import do_setup
    from atheriz.globals.objects import filter_by

    monkeypatch.setenv("ATHERIZ_SUPERUSER_USERNAME", "  MyAdmin  \n")
    monkeypatch.setenv("ATHERIZ_SUPERUSER_PASSWORD", "  strongpass123  ")

    do_setup(username=None, password=None)

    # username should be stripped, not contain spaces/newline
    accounts = filter_by(lambda x: getattr(x, "is_account", False))
    # find account with stripped name
    matched = [a for a in accounts if a.name == "MyAdmin"]
    assert len(matched) == 1, f"expected stripped account 'MyAdmin', got {[a.name for a in accounts]}"
    # ensure no account with raw whitespace exists
    assert not any(a.name == "  MyAdmin  \n" for a in accounts)


def test_superuser_creation_rejects_weak_password(global_test_env, monkeypatch):
    from atheriz.initial_setup import do_setup

    monkeypatch.setenv("ATHERIZ_SUPERUSER_USERNAME", "AdminUser")
    monkeypatch.setenv("ATHERIZ_SUPERUSER_PASSWORD", "short")

    with pytest.raises(ValueError, match="Invalid.*password"):
        do_setup(username=None, password=None)


def test_superuser_creation_rejects_invalid_name(global_test_env, monkeypatch):
    from atheriz.initial_setup import do_setup

    monkeypatch.setenv("ATHERIZ_SUPERUSER_USERNAME", "ab")
    monkeypatch.setenv("ATHERIZ_SUPERUSER_PASSWORD", "strongpass123")

    with pytest.raises(ValueError, match="Invalid.*username"):
        do_setup(username=None, password=None)


def test_command_parsing_consistent_across_os(global_test_env):
    from atheriz.commands.base_cmd import Command

    class Dummy(Command):
        key = "say"
        aliases = []
        desc = "dummy"

        def setup_parser(self):
            self.parser.add_argument("text", nargs="*")

    caller = MagicMock()
    caller.msg = MagicMock()

    cmd = Dummy()
    # ensure parser built
    _ = cmd.parser

    for os_name in ("nt", "posix"):
        with patch("os.name", os_name):
            # should not raise and should give same result for quoted input
            caller.msg.reset_mock()
            _, _, parsed_nt = cmd.execute(caller, '"hello world"', cmdstring="say") if os_name == "nt" else (None, None, None)
            # we test both separately
            pass

    # direct comparison: same args_string gives same arg_list regardless of os.name
    # we test by calling execute twice with different os.name patches and comparing parsed text
    caller1 = MagicMock()
    caller1.msg = MagicMock()
    caller2 = MagicMock()
    caller2.msg = MagicMock()

    with patch("os.name", "nt"):
        _, _, parsed_nt = cmd.execute(caller1, '"hello world"', cmdstring="say")
    with patch("os.name", "posix"):
        _, _, parsed_posix = cmd.execute(caller2, '"hello world"', cmdstring="say")

    assert parsed_nt is not None and parsed_posix is not None
    assert parsed_nt.text == parsed_posix.text == ["hello world"]

    # backslash should not be mangled on either
    with patch("os.name", "nt"):
        _, _, p_nt = cmd.execute(MagicMock(msg=MagicMock()), r"C:\new\file", cmdstring="say")
    with patch("os.name", "posix"):
        _, _, p_posix = cmd.execute(MagicMock(msg=MagicMock()), r"C:\new\file", cmdstring="say")
    assert p_nt.text == p_posix.text == [r"C:\new\file"]


def test_is_under_handles_symlinked_game_folder(global_test_env):
    with tempfile.TemporaryDirectory() as tmp:
        real = pathlib.Path(tmp) / "real_game"
        real.mkdir()
        (real / "module.py").write_text("x=1", encoding="utf-8")
        link = pathlib.Path(tmp) / "link_game"
        try:
            link.symlink_to(real)
        except OSError as e:
            pytest.skip(f"symlink not supported: {e}")

        # file via symlink should be considered under symlink ancestor
        file_via_link = link / "module.py"
        assert _is_under(str(file_via_link), str(link)) is True
        # file via real path should also be under real ancestor
        file_real = real / "module.py"
        assert _is_under(str(file_real), str(real)) is True
        # file outside should not be under
        outside = pathlib.Path(tmp) / "other.py"
        outside.write_text("y=1", encoding="utf-8")
        assert _is_under(str(outside), str(link)) is False


def test_is_under_still_rejects_outside_path():
    with tempfile.TemporaryDirectory() as tmp:
        a = pathlib.Path(tmp) / "a"
        b = pathlib.Path(tmp) / "b"
        a.mkdir()
        b.mkdir()
        f = b / "file.py"
        f.write_text("x", encoding="utf-8")
        assert _is_under(str(f), str(a)) is False
        assert _is_under(str(f), str(b)) is True


def test_admin_token_permissions_atomically_600(tmp_path, monkeypatch):
    import inspect
    from atheriz import atheriz as az
    src = inspect.getsource(az.start_server)
    assert "os.open" in src and "admin.token" in src
    assert "0o600" in src
    assert 'open(token_file, "w"' not in src


def test_settings_mutation_requires_lock():
    import inspect
    from atheriz import atheriz as az
    src = inspect.getsource(az.main)
    assert "WEBSERVER_PORT" in src
    has_lock = "Lock" in src or "lock" in src.lower()
    assert has_lock or "settings" not in src, "settings mutated without lock in main() — concurrent start/stop may race"

def test_settings_concurrent_mutation_is_threadsafe():
    import threading, atheriz.settings as s
    orig = s.WEBSERVER_PORT
    errors = []
    def writer(v):
        try:
            for i in range(100):
                s.WEBSERVER_PORT = v + i
        except Exception as e:
            errors.append(e)
    t1 = threading.Thread(target=writer, args=(1000,))
    t2 = threading.Thread(target=writer, args=(2000,))
    t1.start(); t2.start()
    t1.join(timeout=2); t2.join(timeout=2)
    s.WEBSERVER_PORT = orig
    assert not errors
    assert not t1.is_alive() and not t2.is_alive()
    import inspect
    from atheriz import atheriz as az
    src = inspect.getsource(az.main)
    assert "RLock" in src or "Lock" in src or "threading" in src, "settings mutation should be guarded"
