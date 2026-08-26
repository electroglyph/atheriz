"""Issue tests: real server boot — `start_server()` must boot uvicorn and the
telnet protocol for real, serve the connection screen to a live telnet client,
round-trip a command, and shut down cleanly. Everywhere else in the suite
these paths are mocked; this is the closest thing to `atheriz start` short of
spawning a subprocess.

Ports: always ephemeral (bind 127.0.0.1:0 and read the port) so the test can
never collide with a server already running on the defaults (4444/9999).

Flake hardening: this test shares the process with 2.7k other tests that
mutate globals (_ALL_OBJECTS, _ASYNC_THREAD_POOL, _ASYNC_TICKER,
server_state, SAVE_PATH). In isolation it passes in 0.6s; in the full suite
under load it can take >15s to bind or to drain. All blocking waits are
bounded with `asyncio.wait_for` / `thread.join(timeout)` and emit
timestamped diagnostics to stderr so a hang becomes a failing assertion with
thread-dump instead of a silent 60s stall.
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
import time
import threading
import traceback
from pathlib import Path

import pytest
import telnetlib3

import atheriz.atheriz as az
from atheriz import settings
from atheriz.atheriz import request_internal_shutdown, server_state
from atheriz.globals import get as get_singleton
from atheriz.globals import startstop as startstop_module

BOOT_DEADLINE = 25.0  # full suite under load needs more than 15s
READ_TIMEOUT = 10.0
JOIN_TIMEOUT = 20.0
POLL_INTERVAL = 0.1

# Serialize boot tests so two ephemeral boots never race for a port.
_BOOT_LOCK = threading.Lock()


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{ts} test_server_boot] {msg}", file=sys.stderr, flush=True)


def _free_port() -> int:
    """Pick an ephemeral free port (never the configured defaults)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dump_threads() -> str:
    frames = []
    for tid, frame in sys._current_frames().items():
        th = next((t for t in threading.enumerate() if t.ident == tid), None)
        name = th.name if th else f"tid={tid}"
        frames.append(f"--- Thread {name} ({tid}) ---")
        frames.append("".join(traceback.format_stack(frame)))
    return "\n".join(frames)


def _clear_global_pool_and_ticker():
    _log("clear_global_pool_and_ticker: start")
    try:
        pool = get_singleton._ASYNC_THREAD_POOL
        if pool is not None:
            try:
                pool.stop(wait=True, timeout=2)
            except Exception:
                _log(f"pool.stop failed: {traceback.format_exc()}")
        get_singleton._ASYNC_THREAD_POOL = None
    except Exception:
        _log(f"clear pool failed: {traceback.format_exc()}")
    try:
        ticker = get_singleton._ASYNC_TICKER
        if ticker is not None:
            try:
                ticker.clear()
                ticker.stop()
            except Exception:
                _log(f"ticker clear/stop failed: {traceback.format_exc()}")
        get_singleton._ASYNC_TICKER = None
    except Exception:
        _log(f"clear ticker failed: {traceback.format_exc()}")
    try:
        get_singleton._CONNECTION_MANAGER = None
    except Exception:
        pass
    try:
        startstop_module._shutdown_completed = False
    except Exception:
        pass
    # If a prior boot left a uvicorn server behind, ask it to exit.
    try:
        srv = server_state.uvicorn_server
        if srv is not None:
            _log("found leftover uvicorn_server, setting should_exit=True")
            srv.should_exit = True
    except Exception:
        pass
    _log("clear_global_pool_and_ticker: done")


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
        # Hold _BOOT_LOCK across the whole boot so no other boot test can
        # steal the ephemeral port while we are between _free_port() and
        # uvicorn bind (local fix, not a full-suite isolation — autouse
        # global_test_env still runs concurrently, hence the daemon+timeouts).
        if not _BOOT_LOCK.acquire(timeout=5):
            pytest.skip("could not acquire boot lock")
        try:
            self._run_boot(tmp_path, monkeypatch, capsys)
        finally:
            _BOOT_LOCK.release()

    def _run_boot(self, tmp_path, monkeypatch, capsys):
        telnet_port = _free_port()
        web_port = _free_port()
        assert telnet_port != settings.TELNET_PORT
        assert web_port != settings.WEBSERVER_PORT
        _log(f"boot start: telnet={telnet_port} web={web_port} SAVE_PATH={settings.SAVE_PATH}")

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

        thread_exc: list[BaseException] = []

        def _target():
            try:
                _log("server thread: enter start_server")
                az.start_server()
                _log("server thread: start_server returned")
            except BaseException as e:  # capture crash so _wait_for_boot can report it
                thread_exc.append(e)
                _log(f"server thread: crashed: {e}\n{traceback.format_exc()}")

        thread = threading.Thread(target=_target, daemon=True, name="server-boot")
        thread.start()
        _log(f"server thread started: ident={thread.ident}")
        try:
            self._wait_for_boot(telnet_port, tmp_path / "secret", thread, thread_exc)

            _log("telnet session: opening")
            try:
                out = asyncio.run(
                    asyncio.wait_for(self._telnet_session(telnet_port), timeout=READ_TIMEOUT + 5)
                )
            except asyncio.TimeoutError:
                _log(f"telnet session timed out after {READ_TIMEOUT+5}s\n{_dump_threads()}")
                pytest.fail(f"telnet session timed out after {READ_TIMEOUT+5}s")
            _log(f"telnet session: done, out len={len(out)}")

            assert "ATHERIZ VERSION" in out, out
            assert "enter 'connect" in out, out
            assert "Goodbye!" in out, out

            _log(f"request shutdown on web_port={web_port}")
            assert request_internal_shutdown(port=web_port), "internal shutdown request failed"

            _log(f"join server thread {JOIN_TIMEOUT}s")
            thread.join(timeout=JOIN_TIMEOUT)
            if thread.is_alive():
                _log(f"server thread did not exit within {JOIN_TIMEOUT}s\n{_dump_threads()}")
            assert not thread.is_alive(), f"server thread did not exit within {JOIN_TIMEOUT}s after shutdown"
        finally:
            if thread.is_alive():
                _log("server thread still alive in finally, forcing should_exit")
                srv = server_state.uvicorn_server
                if srv is not None:
                    try:
                        srv.should_exit = True
                    except Exception:
                        _log(traceback.format_exc())
                thread.join(timeout=5)
                if thread.is_alive():
                    _log(f"server thread still alive after force join\n{_dump_threads()}")
            server_state.running = False
            server_state.uvicorn_server = None
            az.app.router.lifespan_context = original_lifespan
            _clear_global_pool_and_ticker()
            _log("boot cleanup: done")

        assert not (Path(settings.SAVE_PATH) / "server.pid").exists()
        assert not (Path(settings.SECRET_PATH) / "admin.token").exists()
        # capsys read must not deadlock; server thread is daemon+joined above
        out = capsys.readouterr().out
        assert "Server stopped." in out, f"missing 'Server stopped.' in: {out[:2000]}"
        assert get_singleton._ASYNC_THREAD_POOL is None, (
            "shutdown must drop the global threadpool so a later boot gets a fresh one"
        )
        assert get_singleton._ASYNC_TICKER is None, (
            "shutdown must drop the global ticker so a later boot gets a fresh one"
        )
        _log("test_server_boots_and_serves_telnet: PASS")

    def test_server_refuses_second_instance(
        self, global_test_env, monkeypatch, capsys
    ):
        """A live server.pid must make start_server() refuse to boot again."""
        _log("test_server_refuses_second_instance: start")
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
        _log("test_server_refuses_second_instance: PASS")

    def _wait_for_boot(self, telnet_port: int, secret_dir: Path, thread: threading.Thread, thread_exc: list):
        token = secret_dir / "admin.token"
        deadline = time.monotonic() + BOOT_DEADLINE
        last_error = None
        poll = 0
        while time.monotonic() < deadline:
            poll += 1
            if thread_exc:
                pytest.fail(f"server thread crashed during boot: {thread_exc[0]}\n{traceback.format_exc()}")
            if not thread.is_alive():
                # start_server returned without binding (e.g. pid lock) — fail fast
                pytest.fail("server thread exited before boot completed (see stderr log)")
            if token.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", telnet_port), timeout=1
                    ):
                        _log(f"boot ready after {poll} polls")
                        return
                except OSError as e:
                    last_error = e
            if poll % 10 == 0:
                _log(f"waiting for boot: poll={poll} token_exists={token.exists()} alive={thread.is_alive()} last_error={last_error}")
            time.sleep(POLL_INTERVAL)
        _log(f"boot deadline exceeded {BOOT_DEADLINE}s last_error={last_error}\n{_dump_threads()}")
        pytest.fail(
            f"server did not come up within {BOOT_DEADLINE}s "
            f"(last connect error: {last_error})"
        )

    async def _telnet_session(self, telnet_port: int) -> str:
        _log(f"_telnet_session: open_connection 127.0.0.1:{telnet_port}")
        reader, writer = await asyncio.wait_for(
            telnetlib3.open_connection("127.0.0.1", telnet_port, encoding="utf8"),
            timeout=READ_TIMEOUT,
        )
        _log("_telnet_session: connected, reading ATHERIZ VERSION")
        try:
            out = await self._read_until(reader, "ATHERIZ VERSION", READ_TIMEOUT)
            _log(f"_telnet_session: got banner len={len(out)}")
            writer.write("quit\n")
            try:
                await asyncio.wait_for(writer.drain(), timeout=2)
            except (AttributeError, asyncio.TimeoutError):
                pass
            try:
                out += await asyncio.wait_for(self._read_until(reader, "", READ_TIMEOUT), timeout=READ_TIMEOUT)
            except asyncio.TimeoutError:
                pass
            _log(f"_telnet_session: quit response len={len(out)}")
            return out
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except Exception:
                pass
            _log("_telnet_session: closed")

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
