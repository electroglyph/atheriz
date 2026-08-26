"""Issue tests: real server boot — `start_server()` must boot uvicorn and the
telnet protocol for real, serve the connection screen to a live telnet client,
round-trip a command, and shut down cleanly. Everywhere else in the suite
these paths are mocked; this is the closest thing to `atheriz start` short of
spawning a subprocess.

Ports: always ephemeral (bind 127.0.0.1:0 and read the port) so the test can
never collide with a server already running on the defaults (4444/9999).
"""
from __future__ import annotations

import asyncio
import os
import socket
import time
import threading
from pathlib import Path

import pytest
import telnetlib3

import atheriz.atheriz as az
from atheriz import settings
from atheriz.atheriz import request_internal_shutdown, server_state
from atheriz.globals import get as get_singleton
from atheriz.globals import startstop as startstop_module

BOOT_DEADLINE = 15.0
READ_TIMEOUT = 10.0
JOIN_TIMEOUT = 15.0
POLL_INTERVAL = 0.1


def _free_port() -> int:
    """Pick an ephemeral free port (never the configured defaults)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _clear_global_pool_and_ticker():
    try:
        pool = get_singleton._ASYNC_THREAD_POOL
        if pool is not None:
            try:
                pool.stop(wait=True, timeout=2)
            except Exception:
                pass
        get_singleton._ASYNC_THREAD_POOL = None
    except Exception:
        pass
    try:
        ticker = get_singleton._ASYNC_TICKER
        if ticker is not None:
            try:
                ticker.clear()
                ticker.stop()
            except Exception:
                pass
        get_singleton._ASYNC_TICKER = None
    except Exception:
        pass
    try:
        get_singleton._CONNECTION_MANAGER = None
    except Exception:
        pass
    try:
        startstop_module._shutdown_completed = False
    except Exception:
        pass


class _FakeSignal:
    """start_server() calls signal.signal(), which raises ValueError outside
    the main thread. The server must run on a background thread, so stub it."""

    SIGINT = 2
    SIGTERM = 15

    @staticmethod
    def signal(*_args, **_kwargs):
        return None


class TestServerBoot:
    def test_server_boots_and_serves_telnet(
        self, global_test_env, tmp_path, monkeypatch, capsys
    ):
        telnet_port = _free_port()
        web_port = _free_port()
        assert telnet_port != settings.TELNET_PORT
        assert web_port != settings.WEBSERVER_PORT

        monkeypatch.setattr(settings, "TELNET_PORT", telnet_port)
        monkeypatch.setattr(settings, "WEBSERVER_PORT", web_port)
        monkeypatch.setattr(settings, "TELNET_INTERFACE", "127.0.0.1")
        monkeypatch.setattr(settings, "WEBSERVER_INTERFACE", "127.0.0.1")
        monkeypatch.setattr(settings, "SECRET_PATH", str(tmp_path / "secret"))
        monkeypatch.setattr(az, "setup_game_folder", lambda required=False: None)
        monkeypatch.setattr(az, "signal", _FakeSignal)

        _clear_global_pool_and_ticker()
        server_state.running = False
        server_state.uvicorn_server = None
        original_lifespan = az.app.router.lifespan_context

        thread = threading.Thread(target=az.start_server, daemon=True)
        thread.start()
        try:
            self._wait_for_boot(telnet_port, tmp_path / "secret")

            try:
                out = asyncio.run(asyncio.wait_for(self._telnet_session(telnet_port), timeout=READ_TIMEOUT + 5))
            except asyncio.TimeoutError:
                pytest.fail(f"telnet session timed out after {READ_TIMEOUT+5}s")

            assert "ATHERIZ VERSION" in out, out
            assert "enter 'connect" in out, out
            assert "Goodbye!" in out, out

            assert request_internal_shutdown(port=web_port)

            thread.join(timeout=JOIN_TIMEOUT)
            assert not thread.is_alive(), f"server thread did not exit within {JOIN_TIMEOUT}s after shutdown"
        finally:
            if thread.is_alive():
                srv = server_state.uvicorn_server
                if srv is not None:
                    try:
                        srv.should_exit = True
                    except Exception:
                        pass
                thread.join(timeout=5)
            server_state.running = False
            server_state.uvicorn_server = None
            az.app.router.lifespan_context = original_lifespan
            _clear_global_pool_and_ticker()

        assert not (Path(settings.SAVE_PATH) / "server.pid").exists()
        assert not (Path(settings.SECRET_PATH) / "admin.token").exists()
        assert "Server stopped." in capsys.readouterr().out
        assert get_singleton._ASYNC_THREAD_POOL is None, (
            "shutdown must drop the global threadpool so a later boot gets a fresh one"
        )
        assert get_singleton._ASYNC_TICKER is None, (
            "shutdown must drop the global ticker so a later boot gets a fresh one"
        )

    def test_server_refuses_second_instance(
        self, global_test_env, monkeypatch, capsys
    ):
        """A live server.pid must make start_server() refuse to boot again."""
        monkeypatch.setattr(az, "setup_game_folder", lambda required=False: None)

        pid_file = Path(settings.SAVE_PATH) / "server.pid"
        pid_file.write_text(str(os.getpid()))

        server_state.running = False
        server_state.uvicorn_server = None
        _clear_global_pool_and_ticker()

        az.start_server()

        out = capsys.readouterr().out
        assert "already running" in out.lower()
        assert server_state.uvicorn_server is None
        _clear_global_pool_and_ticker()

    def _wait_for_boot(self, telnet_port: int, secret_dir: Path):
        token = secret_dir / "admin.token"
        deadline = time.monotonic() + BOOT_DEADLINE
        last_error = None
        while time.monotonic() < deadline:
            if token.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", telnet_port), timeout=1
                    ):
                        return
                except OSError as e:
                    last_error = e
            time.sleep(POLL_INTERVAL)
        pytest.fail(
            f"server did not come up within {BOOT_DEADLINE}s "
            f"(last connect error: {last_error})"
        )

    async def _telnet_session(self, telnet_port: int) -> str:
        reader, writer = await asyncio.wait_for(
            telnetlib3.open_connection("127.0.0.1", telnet_port, encoding="utf8"),
            timeout=READ_TIMEOUT,
        )
        try:
            out = await self._read_until(reader, "ATHERIZ VERSION", READ_TIMEOUT)
            writer.write("quit\n")
            try:
                await asyncio.wait_for(writer.drain(), timeout=2)
            except (AttributeError, asyncio.TimeoutError):
                pass
            try:
                out += await asyncio.wait_for(self._read_until(reader, "", READ_TIMEOUT), timeout=READ_TIMEOUT)
            except asyncio.TimeoutError:
                pass
            return out
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except Exception:
                pass

    async def _read_until(self, reader, needle: str, timeout: float) -> str:
        buf = ""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            try:
                line = await asyncio.wait_for(
                    reader.readline(), timeout=remaining
                )
            except asyncio.TimeoutError:
                break
            if isinstance(line, bytes):
                line = line.decode(errors="replace")
            if not line:
                break
            buf += line
            if needle and needle in buf:
                break
        return buf
