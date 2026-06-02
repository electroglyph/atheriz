"""Tests for atheriz.atheriz — ServerState, get_file_version, do_test_command."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atheriz.atheriz import ServerState, get_file_version, server_state


class TestServerState:
    def test_init_defaults(self):
        s = ServerState()
        assert s.running is False
        assert s.uvicorn_server is None

    def test_can_set_running(self):
        s = ServerState()
        s.running = True
        assert s.running is True

    def test_can_assign_uvicorn(self):
        s = ServerState()
        s.uvicorn_server = MagicMock()
        assert s.uvicorn_server is not None

    def test_global_instance_exists(self):
        # INTENT: atheriz module exposes a single server_state instance
        assert server_state is not None
        assert isinstance(server_state, ServerState)


class TestGetFileVersion:
    def test_missing_file_returns_1(self, global_test_env, tmp_path):
        with patch("atheriz.atheriz.static_dir", tmp_path):
            result = get_file_version("nonexistent.css")
        assert result == "1"

    def test_existing_file_returns_mtime(self, global_test_env, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        with patch("atheriz.atheriz.static_dir", tmp_path):
            result = get_file_version("test.txt")
        # mtime as integer string
        assert result.isdigit()
        assert int(result) > 0

    def test_returns_string(self, global_test_env, tmp_path):
        with patch("atheriz.atheriz.static_dir", tmp_path):
            result = get_file_version("anything")
        assert isinstance(result, str)


class TestSetupProtocols:
    def test_registers_listed_protocols(self, global_test_env):
        # INTENT: protocols listed in settings are registered with the app
        from atheriz import atheriz
        app_mock = MagicMock()
        app_mock.websocket.return_value = lambda f: f
        with patch.object(atheriz.settings, "NETWORK_PROTOCOLS",
                          ["atheriz.network.websocket.WebSocketProtocol"]):
            with patch.object(atheriz, "app", app_mock):
                atheriz.setup_protocols()
        app_mock.websocket.assert_called_with("/ws")

    def test_skips_invalid_protocol(self, global_test_env):
        from atheriz import atheriz
        app_mock = MagicMock()
        with patch.object(atheriz.settings, "NETWORK_PROTOCOLS",
                          ["nonexistent.module.NotAClass"]):
            with patch.object(atheriz, "app", app_mock):
                # Should not raise
                atheriz.setup_protocols()
        # No websocket decorator call (we used a fake path)
        # The point is it didn't crash


class TestDoTestCommand:
    def test_runs_core_tests_when_in_core_repo(self, global_test_env):
        # INTENT: when 'core' is in args, core tests are run
        from atheriz.atheriz import do_test_command

        args = MagicMock()
        args.pytest_args = ["core"]

        with patch("atheriz.atheriz.setup_game_folder", return_value=False), \
             patch("pytest.main") as mock_main:
            mock_main.return_value = 0
            with patch("atheriz.atheriz.sys.exit") as mock_exit:
                do_test_command(args)
        # pytest was called
        assert mock_main.called
        # The first arg should include the core test path
        call_args = mock_main.call_args.args[0]
        assert "tests" in " ".join(call_args)

    def test_runs_game_tests_when_in_game_folder(self, global_test_env):
        from atheriz.atheriz import do_test_command
        args = MagicMock()
        args.pytest_args = []
        with patch("atheriz.atheriz.setup_game_folder", return_value=True), \
             patch("pytest.main") as mock_main:
            mock_main.return_value = 0
            with patch("atheriz.atheriz.sys.exit"):
                do_test_command(args)
        assert mock_main.called

    def test_strips_non_flag_args(self, global_test_env):
        # INTENT: when running core tests, non-flag args (positional) are stripped
        from atheriz.atheriz import do_test_command
        args = MagicMock()
        args.pytest_args = ["core", "test_specific.py", "-v"]
        with patch("atheriz.atheriz.setup_game_folder", return_value=False), \
             patch("pytest.main") as mock_main:
            mock_main.return_value = 0
            with patch("atheriz.atheriz.sys.exit"):
                do_test_command(args)
        call_args = mock_main.call_args.args[0]
        # test_specific.py should be stripped (it's not a flag)
        assert "test_specific.py" not in call_args
        # -v is preserved
        assert "-v" in call_args

    def test_adds_warning_ignore(self, global_test_env):
        from atheriz.atheriz import do_test_command
        args = MagicMock()
        args.pytest_args = ["core"]
        with patch("atheriz.atheriz.setup_game_folder", return_value=False), \
             patch("pytest.main") as mock_main:
            mock_main.return_value = 0
            with patch("atheriz.atheriz.sys.exit"):
                do_test_command(args)
        call_args = mock_main.call_args.args[0]
        # -W ignore is prepended
        assert "-W" in call_args
        assert "ignore::pytest.PytestAssertRewriteWarning" in call_args

    def test_exits_with_pytest_return_code(self, global_test_env):
        # INTENT: sys.exit is called with the pytest return code
        from atheriz.atheriz import do_test_command
        args = MagicMock()
        args.pytest_args = ["core"]
        with patch("atheriz.atheriz.setup_game_folder", return_value=False), \
             patch("pytest.main", return_value=42), \
             patch("atheriz.atheriz.sys.exit") as mock_exit:
            do_test_command(args)
        mock_exit.assert_called_once_with(42)


class TestCreateGameData:
    def test_loads_objects_and_calls_setup(self, global_test_env):
        from atheriz.atheriz import create_game_data
        args = MagicMock()
        args.accountname = "alice"
        args.charactername = "Bob"
        args.password = "secret"
        with patch("atheriz.atheriz.setup_game_folder"), \
             patch("atheriz.atheriz.load_objects"), \
             patch("atheriz.atheriz.at_char_create") as mock_char, \
             patch("atheriz.atheriz.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            create_game_data(args)
        mock_char.assert_called_once_with("alice", "Bob", "secret")


class TestSpawnDaemon:
    def test_spawn_subprocess(self, global_test_env, tmp_path):
        from atheriz.atheriz import spawn_daemon
        args = MagicMock()
        args.port = 8000
        args.host = "127.0.0.1"
        args.foreground = False
        # Use real tmp save path so log file can be opened
        with patch("atheriz.settings.SAVE_PATH", str(tmp_path)), \
             patch("atheriz.atheriz.setup_game_folder"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("psutil.pid_exists", return_value=False):
            mock_popen.return_value.pid = 12345
            spawn_daemon(args)
        # A subprocess was spawned
        assert mock_popen.called
        cmd = mock_popen.call_args.args[0]
        assert "atheriz.atheriz" in cmd
        assert "start" in cmd
        assert "--foreground" in cmd

    def test_skips_if_server_already_running(self, global_test_env, tmp_path):
        from atheriz.atheriz import spawn_daemon
        args = MagicMock()
        args.port = None
        args.host = None
        # Pre-create a pid file so the function thinks server is running
        (tmp_path / "server.pid").write_text("99999")
        with patch("atheriz.settings.SAVE_PATH", str(tmp_path)), \
             patch("atheriz.atheriz.setup_game_folder"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("psutil.pid_exists", return_value=True):
            spawn_daemon(args)
        # No new process spawned
        mock_popen.assert_not_called()
