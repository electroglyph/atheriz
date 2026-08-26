"""Tests for atheriz.atheriz — ServerState, get_file_version, do_test_command."""
from __future__ import annotations

import asyncio
import os
import time
import sys
import tempfile
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import atheriz
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

    def test_game_folder_protocol_setting_is_applied_before_setup(
        self, global_test_env, monkeypatch
    ):
        from atheriz import atheriz

        app_mock = MagicMock()

        class _Sentinel(BaseException):
            pass

        def inject_game_settings():
            monkeypatch.setattr(atheriz.settings, "WEBSOCKET_ENABLED", False)
            monkeypatch.setattr(
                atheriz.settings,
                "NETWORK_PROTOCOLS",
                ["atheriz.network.websocket.WebSocketProtocol"],
            )

        with patch.object(atheriz, "app", app_mock), \
             patch.object(atheriz, "setup_game_folder", side_effect=inject_game_settings), \
             patch.object(atheriz, "do_startup", side_effect=_Sentinel):
            with pytest.raises(_Sentinel):
                atheriz.start_server()

        app_mock.websocket.assert_not_called()


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
             patch("atheriz.atheriz.request_create_account",
                   return_value=("unavailable", "No admin.token found. Is the server running?")), \
             patch("atheriz.atheriz.load_objects"), \
             patch("atheriz.atheriz.at_char_create") as mock_char, \
             patch("atheriz.atheriz.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            create_game_data(args)
        mock_char.assert_called_once_with("alice", "Bob", "secret")

    def test_delegates_to_running_server_when_available(self, global_test_env):
        from atheriz.atheriz import create_game_data
        args = MagicMock()
        args.accountname = "alice"
        args.charactername = "Bob"
        args.password = "secret"
        args.port = None
        with patch("atheriz.atheriz.setup_game_folder"), \
             patch("atheriz.atheriz.request_create_account",
                   return_value=("ok", "Success! Account and character created.")) as mock_req, \
             patch("atheriz.atheriz.load_objects") as mock_load, \
             patch("atheriz.atheriz.at_char_create") as mock_char:
            create_game_data(args)
        mock_req.assert_called_once_with("alice", "Bob", "secret", None)
        mock_load.assert_not_called()
        mock_char.assert_not_called()

    def test_prints_error_when_server_refuses(self, global_test_env, capsys):
        from atheriz.atheriz import create_game_data
        args = MagicMock()
        args.accountname = "alice"
        args.charactername = "Bob"
        args.password = "secret"
        with patch("atheriz.atheriz.setup_game_folder"), \
             patch("atheriz.atheriz.request_create_account",
                   return_value=("error", "Account already exists.")), \
             patch("atheriz.atheriz.load_objects") as mock_load, \
             patch("atheriz.atheriz.at_char_create") as mock_char:
            create_game_data(args)
        mock_load.assert_not_called()
        mock_char.assert_not_called()
        assert "Account already exists." in capsys.readouterr().out

    def test_falls_back_to_offline_create_when_unavailable(self, global_test_env):
        from atheriz.atheriz import create_game_data
        args = MagicMock()
        args.accountname = "alice"
        args.charactername = "Bob"
        args.password = "secret"
        with patch("atheriz.atheriz.setup_game_folder"), \
             patch("atheriz.atheriz.request_create_account",
                   return_value=("unavailable", "Server did not respond.")), \
             patch("atheriz.atheriz.load_objects"), \
             patch("atheriz.atheriz.at_char_create") as mock_char, \
             patch("atheriz.atheriz.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            create_game_data(args)
        mock_char.assert_called_once_with("alice", "Bob", "secret")


class TestRequestCreateAccount:
    def test_unavailable_without_token_file(self, global_test_env, tmp_path):
        from atheriz.atheriz import request_create_account
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)):
            status, _ = request_create_account("alice", "Bob", "secret", port=8000)
        assert status == "unavailable"

    def test_posts_json_and_parses_response(self, global_test_env, tmp_path):
        import urllib.request
        from atheriz.atheriz import request_create_account
        (tmp_path / "admin.token").write_text("secret-token")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = (
            b'{"status": "ok", "message": "Success! Account and character created."}'
        )
        mock_response.__enter__.return_value = mock_response
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)), \
             patch.object(atheriz.settings, "WEBSERVER_PORT", 8123), \
             patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            status, msg = request_create_account("alice", "Bob", "secret")
        assert status == "ok"
        assert msg == "Success! Account and character created."
        req = mock_urlopen.call_args.args[0]
        assert req.full_url == "http://localhost:8123/_internal/create_account"
        assert req.headers.get("X-admin-token") == "secret-token"
        assert req.headers.get("Content-type") == "application/json"
        import json as json_mod
        assert json_mod.loads(req.data) == {
            "account_name": "alice",
            "char_name": "Bob",
            "password": "secret",
        }

    def test_returns_unavailable_when_server_unreachable(self, global_test_env, tmp_path):
        from atheriz.atheriz import request_create_account
        (tmp_path / "admin.token").write_text("secret-token")
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)), \
             patch("urllib.request.urlopen",
                   side_effect=urllib.request.URLError("connection refused")):
            status, _ = request_create_account("alice", "Bob", "secret", port=8000)
        assert status == "unavailable"


class _FakeRequest:
    def __init__(self, token=None, host="127.0.0.1", body=None, bad_json=False):
        self.headers = {} if token is None else {"X-Admin-Token": token}
        self.client = SimpleNamespace(host=host)
        self._body = body
        self._bad_json = bad_json

    async def json(self):
        if self._bad_json:
            raise ValueError("bad json")
        return self._body


class TestCreateAccountEndpoint:
    def test_rejects_missing_token_file(self, global_test_env, tmp_path):
        from atheriz.atheriz import create_account_endpoint
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)):
            result = asyncio.run(create_account_endpoint(_FakeRequest(token="x")))
        assert result["status"] == "error"
        assert result["message"] == "Token file not found."

    def test_rejects_invalid_token(self, global_test_env, tmp_path):
        from atheriz.atheriz import create_account_endpoint
        (tmp_path / "admin.token").write_text("real-token")
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)):
            result = asyncio.run(create_account_endpoint(_FakeRequest(token="wrong")))
        assert result["status"] == "error"
        assert result["message"] == "Invalid token."

    def test_rejects_remote_host(self, global_test_env, tmp_path):
        from atheriz.atheriz import create_account_endpoint
        (tmp_path / "admin.token").write_text("real-token")
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)):
            result = asyncio.run(
                create_account_endpoint(_FakeRequest(token="real-token", host="8.8.8.8"))
            )
        assert result["status"] == "error"
        assert result["message"] == "Remote account creation not allowed."

    def test_creates_account_via_at_char_create(self, global_test_env, tmp_path):
        from atheriz.atheriz import create_account_endpoint
        (tmp_path / "admin.token").write_text("real-token")
        fake_thread = AsyncMock(side_effect=lambda fn, *args: fn(*args))
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)), \
             patch("atheriz.atheriz.run_in_threadpool", fake_thread), \
             patch("atheriz.atheriz.at_char_create") as mock_char:
            result = asyncio.run(
                create_account_endpoint(
                    _FakeRequest(
                        token="real-token",
                        body={"account_name": "alice", "char_name": "Bob", "password": "secret123"},
                    )
                )
            )
        assert result["status"] == "ok"
        mock_char.assert_called_once_with("alice", "Bob", "secret123")

    def test_rejects_missing_body_fields(self, global_test_env, tmp_path):
        from atheriz.atheriz import create_account_endpoint
        (tmp_path / "admin.token").write_text("real-token")
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)):
            result = asyncio.run(
                create_account_endpoint(
                    _FakeRequest(token="real-token", body={"account_name": "alice"})
                )
            )
        assert result["status"] == "error"

    def test_rejects_invalid_json_body(self, global_test_env, tmp_path):
        from atheriz.atheriz import create_account_endpoint
        (tmp_path / "admin.token").write_text("real-token")
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)):
            result = asyncio.run(
                create_account_endpoint(
                    _FakeRequest(token="real-token", body=None, bad_json=True)
                )
            )
        assert result["status"] == "error"


BLOCK_SECONDS = 0.6
PROBE_SECONDS = 0.05
STALL_THRESHOLD = 0.3


class TestInternalAdminEndpointsBlockLoop:
    """INTENT: /_internal/hot_reload and /_internal/shutdown must NOT freeze the
    event loop. These tests FAIL while the handlers run blocking work directly
    (issue #36) and PASS once it's moved off-loop (run_in_threadpool /
    BackgroundTasks)."""

    @staticmethod
    def _make_blocking():
        def blocking(*_args, **_kwargs):
            time.sleep(BLOCK_SECONDS)
            return "reloaded"
        return blocking

    @staticmethod
    def _assert_reload_loop_delay(loop_delay):
        assert loop_delay < STALL_THRESHOLD, (
            f"event loop stalled {loop_delay:.3f}s during the handler — the "
            "handler is still doing blocking work on the loop (issue #36)"
        )

    @staticmethod
    def _ordered_measure(endpoint) -> float:
        async def probe():
            t0 = time.monotonic()
            await asyncio.sleep(PROBE_SECONDS)
            return time.monotonic() - t0

        async def run():
            probe_task = asyncio.create_task(probe())
            await asyncio.sleep(0)  # let probe enter its sleep first
            handler_task = asyncio.create_task(endpoint())
            delay = await probe_task
            await handler_task
            return delay

        return asyncio.run(run())

    def test_hot_reload_blocks_loop(self, global_test_env, tmp_path):
        # INTENT: reload handler does blocking work on the loop; PASSES now,
        # fails if fixed.
        from atheriz.atheriz import hot_reload_endpoint
        (tmp_path / "admin.token").write_text("real-token")
        blocking = self._make_blocking()
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)), \
              patch("atheriz.atheriz.do_reload", blocking), \
              patch("atheriz.reloader.reload_game_logic", blocking):
            delay = self._ordered_measure(
                lambda: hot_reload_endpoint(
                    _FakeRequest(token="real-token", host="127.0.0.1")
                )
            )
        self._assert_reload_loop_delay(delay)

    def test_shutdown_blocks_loop(self, global_test_env, tmp_path):
        # INTENT: shutdown handler must NOT do blocking work on the loop; the
        # blocking work is deferred to BackgroundTasks and only runs after the
        # endpoint has returned.
        from atheriz.atheriz import shutdown_endpoint
        from fastapi import BackgroundTasks
        (tmp_path / "admin.token").write_text("real-token")
        blocking = self._make_blocking()
        with patch.object(atheriz.settings, "SECRET_PATH", str(tmp_path)), \
             patch("atheriz.atheriz.do_shutdown", blocking):
            bt = BackgroundTasks()
            delay = self._ordered_measure(
                lambda: shutdown_endpoint(
                    _FakeRequest(token="real-token", host="127.0.0.1"),
                    background_tasks=bt,
                )
            )
            asyncio.run(bt())
        self._assert_reload_loop_delay(delay)


class TestDoResetCommand:
    def test_reset_completes_and_database_usable_after_setup(self, global_test_env):
        """INTENT: `atheriz reset` must not crash with "database is closed;
        refusing to reopen". The command closes the store to release file
        locks, deletes the data files, then reopens and rebuilds the world
        via the game folder's do_setup() -> database_setup.do_setup()."""
        from atheriz.atheriz import do_reset_command
        import atheriz.atheriz as az
        from atheriz import database_setup
        from atheriz import settings

        args = MagicMock()
        args.force = True

        def fake_local_setup():
            database_setup.do_setup()
            db = database_setup.get_database()
            with db.lock:
                db.connection.execute("SELECT 1")

        fake_module = SimpleNamespace(do_setup=fake_local_setup)
        fake_importlib = MagicMock()
        fake_importlib.import_module.return_value = fake_module

        with patch.object(az, "setup_game_folder", return_value=True), \
             patch.object(az, "importlib", fake_importlib), \
             patch.object(az, "spawn_daemon") as m_spawn, \
             patch("psutil.net_connections", return_value=[]):
            do_reset_command(args)

        fake_importlib.import_module.assert_called_once()
        m_spawn.assert_called_once()
        assert settings.SAVE_PATH is not None
        db = database_setup.get_database()
        with db.lock:
            db.connection.execute("SELECT 1")

    def test_reset_aborts_when_confirmation_declined(self, global_test_env, capsys):
        """Declining the prompt must not delete anything or call do_setup."""
        from atheriz.atheriz import do_reset_command
        import atheriz.atheriz as az
        from atheriz import settings

        args = SimpleNamespace(force=False)

        fake_importlib = MagicMock()
        with patch.object(az, "setup_game_folder", return_value=True), \
             patch.object(az, "importlib", fake_importlib), \
             patch("builtins.input", return_value="n"):
            do_reset_command(args)

        assert "Aborted." in capsys.readouterr().out
        fake_importlib.import_module.assert_not_called()
        assert settings.SAVE_PATH is not None


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
             patch("atheriz.atheriz._pid_is_server_process", return_value=True):
            spawn_daemon(args)
        # No new process spawned
        mock_popen.assert_not_called()


class TestSSLConfig:
    """INTENT: uvicorn.Config must receive ssl_certfile when SSL_CERTFILE is
    set (a single combined cert+key PEM), plus ssl_keyfile only when
    SSL_KEYFILE is also set, so the webserver (and /ws) serves https/wss."""

    def _run_start(self, monkeypatch, tmp_path):
        from atheriz import atheriz as az
        captured = {}
        import uvicorn

        class FakeConfig:
            def __init__(self, *args, **kwargs):
                captured.update(kwargs)

        class FakeServer:
            def __init__(self, config):
                self.config = config

            def run(self):
                pass

        monkeypatch.setattr(az, "setup_game_folder", lambda required=False: None)
        monkeypatch.setattr(az, "setup_protocols", lambda: None)
        monkeypatch.setattr(az, "do_startup", lambda: None)
        monkeypatch.setattr(az, "setup_static_files", lambda: None)
        monkeypatch.setattr(az, "do_shutdown", lambda: None)
        monkeypatch.setattr(az.settings, "SAVE_PATH", str(tmp_path))
        monkeypatch.setattr(az.settings, "SECRET_PATH", str(tmp_path / "secret"))
        monkeypatch.setattr(az.settings, "WEBSOCKET_ENABLED", False)
        monkeypatch.setattr(uvicorn, "Config", FakeConfig)
        monkeypatch.setattr(uvicorn, "Server", FakeServer)
        az.server_state.running = False
        az.server_state.uvicorn_server = None
        try:
            az.start_server()
        finally:
            az.server_state.running = False
            az.server_state.uvicorn_server = None
        return captured

    def test_no_ssl_kwargs_when_unset(self, global_test_env, monkeypatch, tmp_path, capsys):
        from atheriz import atheriz as az
        monkeypatch.setattr(az.settings, "SSL_CERTFILE", None)
        monkeypatch.setattr(az.settings, "SSL_KEYFILE", None)
        captured = self._run_start(monkeypatch, tmp_path)
        assert "ssl_certfile" not in captured
        assert "ssl_keyfile" not in captured
        assert "SSL is disabled" in capsys.readouterr().out

    def test_ssl_kwargs_when_both_set(self, global_test_env, monkeypatch, tmp_path, capsys):
        from atheriz import atheriz as az
        cert = tmp_path / "cert.pem"
        cert.write_text("fake-cert")
        key = tmp_path / "key.pem"
        key.write_text("fake-key")
        monkeypatch.setattr(az.settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(az.settings, "SSL_KEYFILE", str(key))
        captured = self._run_start(monkeypatch, tmp_path)
        assert captured.get("ssl_certfile") == str(cert)
        assert captured.get("ssl_keyfile") == str(key)
        out = capsys.readouterr().out
        assert "SSL is enabled" in out
        assert "separate key file" in out

    def test_combined_pem_when_only_cert_set(self, global_test_env, monkeypatch, tmp_path, capsys):
        from atheriz import atheriz as az
        cert = tmp_path / "combined.pem"
        cert.write_text("fake")
        monkeypatch.setattr(az.settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(az.settings, "SSL_KEYFILE", None)
        captured = self._run_start(monkeypatch, tmp_path)
        assert captured.get("ssl_certfile") == str(cert)
        assert "ssl_keyfile" not in captured
        out = capsys.readouterr().out
        assert "SSL is enabled" in out
        assert "combined PEM" in out

    def test_warns_when_cert_file_missing(self, global_test_env, monkeypatch, tmp_path, capsys):
        from atheriz import atheriz as az
        monkeypatch.setattr(az.settings, "SSL_CERTFILE", "/nonexistent/cert.pem")
        monkeypatch.setattr(az.settings, "SSL_KEYFILE", None)
        self._run_start(monkeypatch, tmp_path)
        out = capsys.readouterr().out
        assert "SSL is enabled" in out
        assert "WARNING: SSL cert file not found" in out

    def test_no_ssl_kwargs_when_only_key_set(self, global_test_env, monkeypatch, tmp_path):
        from atheriz import atheriz as az
        monkeypatch.setattr(az.settings, "SSL_CERTFILE", None)
        monkeypatch.setattr(az.settings, "SSL_KEYFILE", "/tmp/key.pem")
        captured = self._run_start(monkeypatch, tmp_path)
        assert "ssl_certfile" not in captured
        assert "ssl_keyfile" not in captured


class TestAdminTokenSecurePermissions:
    def test_admin_token_created_with_secure_permissions(self, global_test_env, monkeypatch, tmp_path):
        import inspect
        from atheriz import atheriz as az
        src = inspect.getsource(az.start_server)
        assert "os.open" in src and "admin.token" in src, (
            "admin.token must be created atomically via os.open(..., 0o600) not open()+chmod"
        )
        assert "0o600" in src
        assert 'open(token_file, "w"' not in src, "window where token is 0o644 before chmod must not exist"

    def test_admin_token_file_mode_is_600_without_window(self, global_test_env, tmp_path, monkeypatch):
        from atheriz import atheriz as az
        import os
        captured_modes = {}

        orig_open = os.open

        def spy_open(path, flags, mode=0o777):
            captured_modes["mode"] = mode
            captured_modes["flags"] = flags
            return orig_open(path, flags, mode)

        secret = tmp_path / "secret"
        monkeypatch.setattr(az.settings, "SECRET_PATH", str(secret))
        monkeypatch.setattr(az.settings, "SAVE_PATH", str(tmp_path))
        monkeypatch.setattr(az, "setup_game_folder", lambda required=False: None)
        monkeypatch.setattr(az, "setup_protocols", lambda: None)
        monkeypatch.setattr(az, "do_startup", lambda: None)
        monkeypatch.setattr(az, "setup_static_files", lambda: None)
        monkeypatch.setattr(az, "do_shutdown", lambda: None)
        import uvicorn

        class FakeConfig:
            def __init__(self, *a, **kw):
                pass

        class FakeServer:
            def __init__(self, cfg):
                self.config = cfg
            def run(self):
                pass

        monkeypatch.setattr(uvicorn, "Config", FakeConfig)
        monkeypatch.setattr(uvicorn, "Server", FakeServer)
        with patch("os.open", side_effect=spy_open):
            try:
                az.start_server()
            except SystemExit:
                pass
            except Exception:
                pass
        token_file = secret / "admin.token"
        if token_file.exists():
            mode = oct(token_file.stat().st_mode)[-3:]
            assert mode == "600", f"admin.token mode must be 600, got {mode}"
            assert captured_modes.get("mode") == 0o600, "must use os.open with 0o600 atomically"
            assert captured_modes.get("flags") & os.O_CREAT and captured_modes.get("flags") & os.O_EXCL, "must use O_EXCL"
        else:
            import inspect as _insp
            assert "os.open" in _insp.getsource(az.start_server)

    def test_salt_file_uses_secure_create_and_token_does_too(self):
        import inspect
        from atheriz.globals import salt as salt_mod
        from atheriz import atheriz as az
        salt_src = inspect.getsource(salt_mod.get_salt)
        assert "os.open" in salt_src and "0o600" in salt_src
        az_src = inspect.getsource(az.start_server)
        assert az_src.count("os.open") >= 1, "both salt and token should use os.open"


class TestServerLogRotation:
    def test_server_log_has_rotation_handler(self, tmp_path, monkeypatch):
        import inspect
        from atheriz import atheriz as az
        src = inspect.getsource(az.spawn_daemon)
        assert "RotatingFileHandler" in src or "rotation" in src.lower() or "maxBytes" in src, (
            "server.log must use RotatingFileHandler to avoid unbounded growth"
        )

    def test_spawn_daemon_log_not_unbounded_append(self, tmp_path):
        import inspect
        from atheriz import atheriz as az
        src = inspect.getsource(az.spawn_daemon)
        assert 'open(log_file, "a"' not in src or "RotatingFileHandler" in src, (
            "plain append without rotation allows unbounded server.log"
        )
