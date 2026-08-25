"""Merged telnet tests — TelnetConnection, lifespan, line cap, TLS."""
from __future__ import annotations

import asyncio
import socket
import ssl
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import telnetlib3

import atheriz.settings as settings
from atheriz.network.telnet import TelnetConnection, TelnetProtocol, _clamp_naws, read_capped_lines, build_telnet_ssl_context
from fastapi import FastAPI


def _make_writer(host="1.2.3.4"):
    writer = MagicMock()
    writer.get_extra_info.return_value = (host, 23)
    return writer


def _make_conn_with_writer(host="1.2.3.4", loop=None):
    w = _make_writer(host)
    conn = TelnetConnection(MagicMock(), w)
    if loop is not None:
        conn.loop = loop
        conn.thread_id = threading.get_ident()
    return conn, w


class _FakeReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, n):
        return self._chunks.pop(0) if self._chunks else ""


def _collect(chunks, max_line=32):
    async def run():
        return [line async for line in read_capped_lines(_FakeReader(chunks), max_line)]

    return asyncio.run(run())


def _make_self_signed(tmp_path) -> tuple[Path, Path, Path]:
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "1", "-nodes", "-subj", "/CN=localhost",
            ],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("openssl not available")
    combined = tmp_path / "combined.pem"
    combined.write_text(cert.read_text() + key.read_text())
    return key, cert, combined


class _LifespanServerStub:
    def __init__(self):
        self._closed = False

    def close(self):
        self._closed = True

    async def wait_closed(self):
        return None


async def _lifespan_fake_create_server(*args, **kwargs):
    return _LifespanServerStub()


class _TlsServerStub:
    def __init__(self):
        self._closed = False

    def close(self):
        self._closed = True

    async def wait_closed(self):
        return None


async def _tls_fake_create_server(*args, **kwargs):
    return _TlsServerStub(), kwargs


def _mount(app):
    @asynccontextmanager
    async def original(app):
        yield

    app.router.lifespan_context = original
    TelnetProtocol.setup(app)
    return app.router.lifespan_context


def _run_lifespan(lifespan, app):
    async def run():
        async with lifespan(app):
            pass

    asyncio.run(run())


class TestTelnetProtocol:
    def test_init_stores_reader_writer(self, global_test_env):
        r, w = MagicMock(), _make_writer()
        conn = TelnetConnection(r, w)
        assert conn.reader is r
        assert conn.writer is w

    def test_init_extracts_host(self, global_test_env):
        w = _make_writer("10.0.0.1")
        conn = TelnetConnection(MagicMock(), w)
        assert conn.client_host == "10.0.0.1"

    def test_init_no_host_defaults_to_question(self, global_test_env):
        w = MagicMock()
        w.get_extra_info.side_effect = Exception("no info")
        conn = TelnetConnection(MagicMock(), w)
        assert conn.client_host == "?"

    def test_session_id(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w, session_id="abc")
        assert conn.session_id == "abc"

    def test_init_pending_state(self, global_test_env):
        conn, _ = _make_conn_with_writer()
        assert conn._pending_bytes == 0
        assert conn._closing is False

    def test_text_command_writes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("text", "hello")
        w.write.assert_called()
        assert any("hello" in str(c.args[0]) for c in w.write.call_args_list)

    def test_prompt_command_writes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("prompt", "> ")
        assert any("> " in str(c.args[0]) for c in w.write.call_args_list)

    def test_unknown_command_silent(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("unknown_cmd", "arg")
        w.write.assert_not_called()
        w.iac.assert_not_called()

    def test_text_no_args(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("text")
        w.write.assert_not_called()

    def test_prompt_no_args(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("prompt")
        w.write.assert_not_called()

    def test_closing_prevents_send(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._closing = True
        conn.send_command("text", "hello")
        w.write.assert_not_called()

    def test_send_from_other_thread_without_loop(self, global_test_env):
        """A connection built outside an event loop (self.loop is None) must
        still deliver a cross-thread send instead of hitting AttributeError."""
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        assert conn.loop is None

        mock_loop = MagicMock()
        def sync_call(func, *args):
            func(*args)
        mock_loop.call_soon_threadsafe.side_effect = sync_call

        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            t = threading.Thread(target=lambda: conn.send_command("text", "hello"))
            t.start()
            t.join()
            w.write.assert_called_once_with("hello")
            assert conn._pending_bytes == 0

    def test_close_calls_writer_close(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.close()
        w.close.assert_called()

    def test_close_idempotent(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.close()
        w.close.reset_mock()
        conn.close()
        w.close.assert_not_called()
        assert conn._closing is True

    def test_close_from_other_thread_schedules(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        assert conn.loop is None
        mock_loop = MagicMock()
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            t = threading.Thread(target=conn.close)
            t.start()
            t.join()
            mock_loop.call_soon_threadsafe.assert_called_once()
            assert mock_loop.call_soon_threadsafe.call_args[0][0] is w.close

    def test_send_after_close_is_noop(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.close()
        w.write.reset_mock()
        w.close.reset_mock()
        conn.send_command("text", "after")
        w.write.assert_not_called()
        w.close.assert_not_called()

    def test_prefers_writer_transport(self, global_test_env):
        w = _make_writer()
        tr = MagicMock()
        tr.get_write_buffer_size.return_value = 42
        w.transport = tr
        w.get_write_buffer_size = MagicMock(return_value=99)
        w._transport = MagicMock()
        w._transport.get_write_buffer_size.return_value = 100
        conn = TelnetConnection(MagicMock(), w)
        assert conn._get_write_buffer_size() == 42
        tr.get_write_buffer_size.assert_called_once()

    def test_falls_back_to_writer(self, global_test_env):
        w = _make_writer()
        w.transport = None
        w.get_write_buffer_size = MagicMock(return_value=77)
        conn = TelnetConnection(MagicMock(), w)
        conn.writer = w
        assert conn._get_write_buffer_size() == 77

    def test_falls_back_to_underscore_transport(self, global_test_env):
        w = _make_writer()
        w.transport = None
        del w.get_write_buffer_size
        tr2 = MagicMock()
        tr2.get_write_buffer_size.return_value = 55
        w._transport = tr2
        conn = TelnetConnection(MagicMock(), w)
        assert conn._get_write_buffer_size() == 55

    def test_returns_none_when_no_transport(self, global_test_env):
        w = _make_writer()
        w.transport = None
        del w.get_write_buffer_size
        w._transport = None
        conn = TelnetConnection(MagicMock(), w)
        assert conn._get_write_buffer_size() is None

    def test_returns_none_on_exception(self, global_test_env):
        w = _make_writer()
        tr = MagicMock()
        tr.get_write_buffer_size.side_effect = RuntimeError("boom")
        w.transport = tr
        conn = TelnetConnection(MagicMock(), w)
        assert conn._get_write_buffer_size() is None

    def test_returns_none_when_writer_missing_attr(self, global_test_env):
        class W:
            def get_extra_info(self, *a, **kw):
                return ("1.2.3.4", 23)
        w = W()
        conn = TelnetConnection(MagicMock(), w)
        assert conn._get_write_buffer_size() is None

    def test_on_loop_pre_buffer_exceeds_closes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        mock_tr = MagicMock()
        mock_tr.get_write_buffer_size.return_value = settings.TELNET_MAX_PENDING_BYTES + 1
        w.transport = mock_tr
        conn.close = MagicMock(wraps=conn.close)
        conn.send_command("text", "hello")
        w.write.assert_not_called()
        conn.close.assert_called_once()

    def test_on_loop_post_buffer_exceeds_closes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        mock_tr = MagicMock()
        mock_tr.get_write_buffer_size.side_effect = [0, settings.TELNET_MAX_PENDING_BYTES + 1]
        w.transport = mock_tr
        conn.close = MagicMock(wraps=conn.close)
        conn.send_command("text", "hello")
        w.write.assert_called_once_with("hello")
        conn.close.assert_called_once()

    def test_on_loop_buffer_none_allows_write(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        w.transport = None
        if hasattr(w, "get_write_buffer_size"):
            del w.get_write_buffer_size
        w._transport = None
        conn.send_command("text", "hi")
        w.write.assert_called_once_with("hi")

    def test_on_loop_write_exception_closes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        w.transport = None
        if hasattr(w, "get_write_buffer_size"):
            del w.get_write_buffer_size
        w._transport = None
        w.write.side_effect = RuntimeError("boom")
        conn.close = MagicMock(wraps=conn.close)
        conn.send_command("text", "hello")
        conn.close.assert_called_once()

    def test_on_loop_pending_not_used(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        w.transport = None
        if hasattr(w, "get_write_buffer_size"):
            del w.get_write_buffer_size
        w._transport = None
        conn._pending_bytes = 999999
        conn.send_command("text", "hi")
        w.write.assert_called_once()
        assert conn._pending_bytes == 999999

    def test_offloop_reserves_and_schedules(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        mock_loop = MagicMock()
        calls = []
        def rec(func, *args):
            calls.append((func.__name__, args))
            func(*args)
        mock_loop.call_soon_threadsafe.side_effect = rec
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            with patch.object(conn, "_get_write_buffer_size", return_value=0):
                conn.send_command("text", "hello")
        assert w.write.call_count == 1
        assert conn._pending_bytes == 0
        assert any(n == "_offloop_write" for n, _ in calls)

    def test_offloop_pending_exceeds_closes_without_schedule(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        conn._pending_bytes = settings.TELNET_MAX_PENDING_BYTES - 2
        mock_loop = MagicMock()
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            conn.send_command("text", "hello")
        assert mock_loop.call_soon_threadsafe.call_count == 1
        assert mock_loop.call_soon_threadsafe.call_args[0][0] is w.close
        assert conn._closing is True

    def test_offloop_schedule_exception_rollbacks(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        mock_loop = MagicMock()
        mock_loop.call_soon_threadsafe.side_effect = RuntimeError("boom")
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            conn.send_command("text", "hello")
        assert conn._pending_bytes == 0
        assert conn._closing is True

    def test_offloop_write_checks_buffer_before_write(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._pending_bytes = 5
        with patch.object(conn, "_get_write_buffer_size", return_value=settings.TELNET_MAX_PENDING_BYTES + 1):
            conn._offloop_write("hello", 5)
        w.write.assert_not_called()
        assert conn._closing is True
        assert conn._pending_bytes == 0

    def test_offloop_write_checks_buffer_after_write(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._pending_bytes = 5
        with patch.object(conn, "_get_write_buffer_size", side_effect=[0, settings.TELNET_MAX_PENDING_BYTES + 1]):
            conn._offloop_write("hello", 5)
        w.write.assert_called_once_with("hello")
        assert conn._closing is True
        assert conn._pending_bytes == 0

    def test_offloop_write_always_decrements_on_exception(self, global_test_env):
        w = _make_writer()
        w.write.side_effect = RuntimeError("boom")
        conn = TelnetConnection(MagicMock(), w)
        conn._pending_bytes = 5
        with patch.object(conn, "_get_write_buffer_size", return_value=0):
            conn._offloop_write("hello", 5)
        assert conn._pending_bytes == 0
        assert conn._closing is True

    def test_offloop_iac_decrements_when_nb_given(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._pending_bytes = 3
        conn._offloop_iac(telnetlib3.telopt.WILL, telnetlib3.telopt.ECHO, nb=3)
        assert conn._pending_bytes == 0
        w.iac.assert_called_once()

    def test_offloop_iac_no_decrement_when_nb_zero(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._pending_bytes = 3
        conn._offloop_iac(telnetlib3.telopt.WILL, telnetlib3.telopt.ECHO)
        assert conn._pending_bytes == 3

    def test_offloop_concurrent_reserve_atomic(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        mock_loop = MagicMock()
        mock_loop.call_soon_threadsafe.side_effect = lambda f, *a: None
        orig = settings.TELNET_MAX_PENDING_BYTES
        try:
            settings.TELNET_MAX_PENDING_BYTES = 10
            conn._pending_bytes = 0
            with patch.object(conn, "_resolve_loop", return_value=mock_loop):
                conn.send_command("text", "12345")
                assert conn._pending_bytes == 5
                conn.send_command("text", "12345")
                assert conn._pending_bytes == 10
                conn.send_command("text", "12345")
                assert conn._closing is True
                assert mock_loop.call_soon_threadsafe.call_count == 3
                assert mock_loop.call_soon_threadsafe.call_args_list[0][0][0].__name__ == "_offloop_write"
                assert mock_loop.call_soon_threadsafe.call_args_list[1][0][0].__name__ == "_offloop_write"
                assert mock_loop.call_soon_threadsafe.call_args_list[2][0][0] is w.close
        finally:
            settings.TELNET_MAX_PENDING_BYTES = orig

    def test_prompt_masked_on_loop_writes_iac_and_text(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        with patch.object(conn, "_get_write_buffer_size", return_value=0):
            conn.send_command("prompt_masked", "secret")
        w.iac.assert_called_once_with(telnetlib3.telopt.WILL, telnetlib3.telopt.ECHO)
        w.write.assert_called_once_with("secret")

    def test_prompt_masked_on_loop_buffer_pre_close(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        with patch.object(conn, "_get_write_buffer_size", return_value=settings.TELNET_MAX_PENDING_BYTES + 1):
            conn.send_command("prompt_masked", "secret")
        w.iac.assert_not_called()
        w.write.assert_not_called()
        assert conn._closing is True

    def test_prompt_masked_offloop_schedules_both(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        mock_loop = MagicMock()
        calls = []
        def rec(func, *args):
            calls.append(func.__name__)
            with patch.object(conn, "_get_write_buffer_size", return_value=0):
                func(*args)
        mock_loop.call_soon_threadsafe.side_effect = rec
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            with patch.object(conn, "_get_write_buffer_size", return_value=0):
                conn.send_command("prompt_masked", "sec")
        assert "_offloop_iac" in calls
        assert "_offloop_write" in calls
        assert conn._pending_bytes == 0

    def test_prompt_masked_offloop_pending_exceeds(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        conn._pending_bytes = settings.TELNET_MAX_PENDING_BYTES - 2
        mock_loop = MagicMock()
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            conn.send_command("prompt_masked", "hello")
        assert mock_loop.call_soon_threadsafe.call_count == 1
        assert mock_loop.call_soon_threadsafe.call_args[0][0] is w.close
        assert conn._closing is True

    def test_prompt_masked_no_text_offloop_only_iac(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        mock_loop = MagicMock()
        mock_loop.call_soon_threadsafe.side_effect = lambda f, *a: f(*a)
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            with patch.object(conn, "_get_write_buffer_size", return_value=0):
                conn.send_command("prompt_masked", "")
                assert conn._pending_bytes == 0
        assert mock_loop.call_soon_threadsafe.call_count == 1
        assert mock_loop.call_soon_threadsafe.call_args[0][0].__name__ == "_offloop_iac"

    def test_echo_on_on_loop(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = threading.get_ident()
        conn.send_command("echo_on")
        w.iac.assert_called_once_with(telnetlib3.telopt.WONT, telnetlib3.telopt.ECHO)

    def test_echo_on_offloop(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.thread_id = 999999
        mock_loop = MagicMock()
        mock_loop.call_soon_threadsafe.side_effect = lambda f, *a: f(*a)
        with patch.object(conn, "_resolve_loop", return_value=mock_loop):
            conn.send_command("echo_on")
        mock_loop.call_soon_threadsafe.assert_called_once()
        assert mock_loop.call_soon_threadsafe.call_args[0][0].__name__ == "_offloop_iac"
        w.iac.assert_called_once()

    def test_echo_on_after_close_noop(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._closing = True
        conn.send_command("echo_on")
        w.iac.assert_not_called()

    def test_prompt_masked_after_close_noop(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn._closing = True
        conn.send_command("prompt_masked", "hi")
        w.iac.assert_not_called()
        w.write.assert_not_called()

    def test_setup_skipped_when_disabled(self, global_test_env):
        app = MagicMock()
        with patch("atheriz.settings.TELNET_ENABLED", False):
            TelnetProtocol.setup(app)
        app.router.lifespan_context.assert_not_called()

    def test_setup_registers_lifespan(self, global_test_env):
        class _Router:
            def __init__(self):
                self.lifespan_context = None

        app = MagicMock()
        app.router = _Router()
        with patch("atheriz.settings.TELNET_ENABLED", True):
            TelnetProtocol.setup(app)
        assert callable(app.router.lifespan_context)

    def test_normal_values_pass_through(self):
        assert _clamp_naws(24, 80) == (24, 80)

    def test_clamps_respect_settings(self):
        """Changing settings values changes clamping behavior."""
        original_min_cols = settings.TELNET_NAWS_MIN_COLS
        original_max_cols = settings.TELNET_NAWS_MAX_COLS
        original_min_rows = settings.TELNET_NAWS_MIN_ROWS
        original_max_rows = settings.TELNET_NAWS_MAX_ROWS
        try:
            settings.TELNET_NAWS_MIN_COLS = 40
            settings.TELNET_NAWS_MAX_COLS = 200
            settings.TELNET_NAWS_MIN_ROWS = 10
            settings.TELNET_NAWS_MAX_ROWS = 50

            assert _clamp_naws(24, 80) == (24, 80)
            assert _clamp_naws(1, 10) == (10, 40)
            assert _clamp_naws(999, 999) == (50, 200)
            assert _clamp_naws(10, 40) == (10, 40)
            assert _clamp_naws(50, 200) == (50, 200)
        finally:
            settings.TELNET_NAWS_MIN_COLS = original_min_cols
            settings.TELNET_NAWS_MAX_COLS = original_max_cols
            settings.TELNET_NAWS_MIN_ROWS = original_min_rows
            settings.TELNET_NAWS_MAX_ROWS = original_max_rows


class TestTelnetLifespan:
    def test_mounting_telnet_preserves_previous_lifespan(self, global_test_env):
        """INTENT: telnet's lifespan must be composed with an existing one, not
        replace it. Today `app.router.lifespan_context` is overwritten so the
        sentinel lifespan's start/stop hooks never run -> FAIL."""
        app = FastAPI()
        calls = []

        @asynccontextmanager
        async def original(app):
            calls.append("start")
            yield
            calls.append("stop")

        app.router.lifespan_context = original

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_lifespan_fake_create_server):
            TelnetProtocol.setup(app)

            installed = app.router.lifespan_context

            async def run():
                async with installed(app):
                    pass

            asyncio.run(run())

        assert calls == ["start", "stop"], (
            f"the pre-installed lifespan was dropped by {TelnetProtocol.__name__}.setup; calls={calls}"
        )

    def test_setup_composes_server_lifecycle_with_previous(self, global_test_env):
        """INTENT: an existing lifespan keeps running AND the telnet server
        starts/stops inside it; the server task must not be a class attribute
        shared across app instances."""
        app = FastAPI()
        calls = []

        @asynccontextmanager
        async def original(app):
            calls.append("start")
            yield
            calls.append("stop")

        app.router.lifespan_context = original

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_lifespan_fake_create_server):
            TelnetProtocol.setup(app)

            installed = app.router.lifespan_context

            async def run():
                async with installed(app):
                    calls.append("inside")

            asyncio.run(run())

        assert calls == ["start", "inside", "stop"], (
            f"composed lifespan ran out of order; calls={calls}"
        )
        assert not hasattr(TelnetProtocol, "_server_task"), (
            "server task must be per-app (closure), not a class attribute"
        )


class TestTelnetLineCap:
    def test_lines_pass_through_without_terminators(self):
        assert _collect(["hello\r\n", "wor", "ld\n"]) == ["hello", "world"]

    def test_cr_nul_and_bare_cr_are_terminators(self):
        assert _collect(["a\r\x00b\n", "c\r"]) == ["a", "b", "c"]

    def test_partial_line_at_eof_is_yielded(self):
        assert _collect(["part"]) == ["part"]

    def test_empty_input_yields_nothing(self):
        assert _collect([""]) == []

    def test_single_overlong_line_dropped(self):
        assert _collect(["x" * 40 + "\n", "ok\n"]) == [None, "ok"]

    def test_terminatorless_flood_stays_bounded_and_dropped(self):
        """INTENT: the failing case for readline() — many chunks with no
        terminator. Buffering must stay capped and the line must be dropped
        once the terminator arrives."""
        chunks = ["x" * 40, "y" * 40, "z" * 40, "\n", "ok\n"]
        assert _collect(chunks) == [None, "ok"]

    def test_max_line_boundary_is_kept(self):
        assert _collect(["x" * 32 + "\n"]) == ["x" * 32]
        assert _collect(["x" * 33 + "\n"]) == [None]

    def test_following_line_unaffected_by_drop(self):
        assert _collect(["A" * 50 + "\r\n", "fine\n"]) == [None, "fine"]


class TestTelnetTLS:
    def test_none_when_cert_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "SSL_CERTFILE", None)
        assert build_telnet_ssl_context() is None

    def test_none_when_cert_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "SSL_CERTFILE", "/nonexistent/cert.pem")
        assert build_telnet_ssl_context() is None

    def test_loads_combined_pem(self, monkeypatch, tmp_path):
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        context = build_telnet_ssl_context()
        assert context is not None
        assert isinstance(context, ssl.SSLContext)

    def test_loads_separate_key(self, monkeypatch, tmp_path):
        key, cert, _ = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(settings, "SSL_KEYFILE", str(key))
        context = build_telnet_ssl_context()
        assert context is not None

    def test_none_when_key_missing(self, monkeypatch, tmp_path):
        key, cert, _ = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(settings, "SSL_KEYFILE", str(tmp_path / "missing.key"))
        assert build_telnet_ssl_context() is None

    def test_passes_ssl_and_tls_auto_when_enabled(self, monkeypatch, tmp_path, global_test_env):
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "TELNET_TLS_ENABLED", True)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        captured = {}

        async def _fake(*args, **kwargs):
            captured.update(kwargs)
            return _TlsServerStub()

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake):
            app = FastAPI()
            lifespan = _mount(app)
            _run_lifespan(lifespan, app)
        assert isinstance(captured.get("ssl"), ssl.SSLContext)
        assert captured.get("tls_auto") is True

    def test_no_ssl_kwargs_when_disabled(self, monkeypatch, tmp_path, global_test_env):
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "TELNET_TLS_ENABLED", False)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        captured = {}

        async def _fake(*args, **kwargs):
            captured.update(kwargs)
            return _TlsServerStub()

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake):
            app = FastAPI()
            lifespan = _mount(app)
            _run_lifespan(lifespan, app)
        assert "ssl" not in captured
        assert "tls_auto" not in captured

    def test_warns_and_plaintext_when_cert_missing(self, monkeypatch, global_test_env):
        monkeypatch.setattr(settings, "TELNET_TLS_ENABLED", True)
        monkeypatch.setattr(settings, "SSL_CERTFILE", "/nonexistent/cert.pem")
        captured = {}

        async def _fake(*args, **kwargs):
            captured.update(kwargs)
            return _TlsServerStub()

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake):
            app = FastAPI()
            lifespan = _mount(app)
            _run_lifespan(lifespan, app)
        assert "ssl" not in captured
        assert "tls_auto" not in captured

    def _free_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def test_tls_and_plaintext_coexist_on_same_port(self, monkeypatch, tmp_path, global_test_env):
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        port = self._free_port()

        async def shell(reader, writer):
            writer.write("hello from secure server\n")
            await asyncio.wait_for(reader.readline(), 10)

        async def run():
            server = await telnetlib3.create_server(
                host="127.0.0.1", port=port, shell=shell,
                ssl=build_telnet_ssl_context(), tls_auto=True,
            )
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await telnetlib3.open_connection(
                    "127.0.0.1", port, ssl=ctx)
                line = await asyncio.wait_for(reader.readline(), 10)
                assert "hello" in line, f"TLS client failed: {line!r}"
                writer.close()
                reader2, writer2 = await telnetlib3.open_connection("127.0.0.1", port)
                line2 = await asyncio.wait_for(reader2.readline(), 10)
                assert "hello" in line2, f"plain client failed: {line2!r}"
                writer2.close()
            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())

    def test_bad_tls_handshake_does_not_kill_server(self, monkeypatch, tmp_path, global_test_env):
        _, _, cert = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        port = self._free_port()

        async def shell(reader, writer):
            writer.write("still alive\n")
            await asyncio.sleep(3)

        async def run():
            server = await telnetlib3.create_server(
                host="127.0.0.1", port=port, shell=shell,
                ssl=build_telnet_ssl_context(), tls_auto=True,
            )
            try:
                raw = socket.create_connection(("127.0.0.1", port))
                raw.sendall(b"\x16\x03\x01\x00\x10" + b"\x00" * 16)
                raw.close()
                await asyncio.sleep(0.3)
                reader, writer = await telnetlib3.open_connection("127.0.0.1", port)
                line = await asyncio.wait_for(reader.readline(), 10)
                assert "still alive" in line, line
                writer.close()
            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())
