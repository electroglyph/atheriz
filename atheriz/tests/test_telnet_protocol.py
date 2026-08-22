"""Tests for atheriz.network.telnet — TelnetConnection and TelnetProtocol."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import threading
import time
import telnetlib3

from atheriz.network.telnet import TelnetConnection, TelnetProtocol, _clamp_naws
import atheriz.settings as settings


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


class TestTelnetConnection:
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


class TestTelnetConnectionSendCommand:
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


class TestTelnetConnectionClose:
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


class TestGetWriteBufferSize:
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
        w = MagicMock()
        w.get_extra_info.return_value = ("1.2.3.4", 23)
        # no transport attrs
        del w.transport
        del w._transport
        if hasattr(w, "get_write_buffer_size"):
            del w.get_write_buffer_size
        conn = TelnetConnection(MagicMock(), w)
        # MagicMock will create attrs on access, so force real missing by using spec
        w2 = _make_writer()
        w2.transport = None
        if hasattr(w2, "get_write_buffer_size"):
            del w2.get_write_buffer_size
        w2._transport = None
        conn.writer = w2
        assert conn._get_write_buffer_size() is None


class TestTelnetBackpressureOnLoop:
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


class TestTelnetBackpressureOffLoop:
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
        # exceeded pending → close() schedules writer.close, not _offloop_write
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
                # 2 writes + 1 close
                assert mock_loop.call_soon_threadsafe.call_count == 3
                assert mock_loop.call_soon_threadsafe.call_args_list[0][0][0].__name__ == "_offloop_write"
                assert mock_loop.call_soon_threadsafe.call_args_list[1][0][0].__name__ == "_offloop_write"
                assert mock_loop.call_soon_threadsafe.call_args_list[2][0][0] is w.close
        finally:
            settings.TELNET_MAX_PENDING_BYTES = orig


class TestTelnetPromptMaskedEchoOn:
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
            # for _offloop_write decrement pending, mock buffer
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
        # exceeded → close() schedules writer.close, not iac/write
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
                # No pending increment for empty text
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


class TestTelnetProtocolSetup:
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


class TestClampNaws:
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
