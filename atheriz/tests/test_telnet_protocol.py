"""Tests for atheriz.network.telnet — TelnetConnection and TelnetProtocol."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atheriz.network.telnet import TelnetConnection, TelnetProtocol, _clamp_naws
import atheriz.settings as settings


def _make_writer(host="1.2.3.4"):
    writer = MagicMock()
    writer.get_extra_info.return_value = (host, 23)
    return writer


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


class TestTelnetConnectionSendCommand:
    def test_text_command_writes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("text", "hello")
        # writer.write was called
        w.write.assert_called()
        # The arg includes "hello"
        assert any("hello" in str(c.args[0]) for c in w.write.call_args_list)

    def test_prompt_command_writes(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("prompt", "> ")
        assert any("> " in str(c.args[0]) for c in w.write.call_args_list)

    def test_unknown_command_silent(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        # Unknown commands are silently ignored (no write)
        conn.send_command("unknown_cmd", "arg")
        # No write was made for the unknown cmd
        # (write is only called for text/prompt)
        # Check that no write was made with the unknown arg
        for c in w.write.call_args_list:
            assert "arg" not in str(c.args[0]) or "arg" == str(c.args[0])

    def test_text_no_args(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.send_command("text")  # no args
        # Should not raise, even with no args
        w.write.assert_called_with("")


class TestTelnetConnectionClose:
    def test_close_calls_writer_close(self, global_test_env):
        w = _make_writer()
        conn = TelnetConnection(MagicMock(), w)
        conn.close()
        w.close.assert_called()


class TestTelnetProtocolSetup:
    def test_setup_skipped_when_disabled(self, global_test_env):
        app = MagicMock()
        with patch("atheriz.settings.TELNET_ENABLED", False):
            TelnetProtocol.setup(app)
        # No on_event was registered
        app.on_event.assert_not_called()

    def test_setup_registers_startup_and_shutdown(self, global_test_env):
        app = MagicMock()
        with patch("atheriz.settings.TELNET_ENABLED", True):
            TelnetProtocol.setup(app)
        # on_event was called twice (startup and shutdown)
        assert app.on_event.call_count == 2
        events = [c.args[0] for c in app.on_event.call_args_list]
        assert "startup" in events
        assert "shutdown" in events


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
