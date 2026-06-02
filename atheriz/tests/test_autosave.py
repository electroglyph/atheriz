"""Tests for atheriz.globals.autosave — autosave_tick, start/stop_autosave."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import atheriz.globals.autosave as autosave_mod
import atheriz.settings as settings


@pytest.fixture
def reset_autosave_started():
    autosave_mod._autosave_started = False
    yield
    autosave_mod._autosave_started = False


class TestIntervalSeconds:
    def test_default_zero(self, monkeypatch, reset_autosave_started):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 0)
        assert autosave_mod._interval_seconds() == 0.0

    def test_one_minute(self, monkeypatch, reset_autosave_started):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 1)
        assert autosave_mod._interval_seconds() == 60.0

    def test_ten_minutes(self, monkeypatch, reset_autosave_started):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 10)
        assert autosave_mod._interval_seconds() == 600.0

    def test_fractional_minute(self, monkeypatch, reset_autosave_started):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 0.5)
        assert autosave_mod._interval_seconds() == 30.0


class TestAutosaveTick:
    def test_calls_save_objects(self, reset_autosave_started):
        with patch("atheriz.globals.autosave.save_objects") as mock_save, \
             patch("atheriz.globals.autosave.get_map_handler") as mock_map, \
             patch("atheriz.globals.autosave.get_node_handler") as mock_node, \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            autosave_mod.autosave_tick()
            mock_save.assert_called_once()

    def test_calls_map_handler_save(self, reset_autosave_started):
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler") as mock_map, \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            autosave_mod.autosave_tick()
            mock_map.return_value.save.assert_called_once()

    def test_calls_node_handler_save(self, reset_autosave_started):
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler") as mock_node, \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            autosave_mod.autosave_tick()
            mock_node.return_value.save.assert_called_once()

    def test_time_system_save_when_enabled(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "TIME_SYSTEM_ENABLED", True)
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None), \
             patch("atheriz.globals.get.get_game_time") as mock_time:
            autosave_mod.autosave_tick()
            mock_time.return_value.save.assert_called_once()

    def test_time_system_save_when_disabled(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "TIME_SYSTEM_ENABLED", False)
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None), \
             patch("atheriz.globals.get.get_game_time") as mock_time:
            autosave_mod.autosave_tick()
            mock_time.return_value.save.assert_not_called()

    def test_broadcasts_to_server_channel(self, reset_autosave_started):
        mock_channel = MagicMock()
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=mock_channel):
            autosave_mod.autosave_tick()
        mock_channel.msg.assert_called()
        # First call should be the success message
        msg = mock_channel.msg.call_args[0][0]
        assert "Autosave completed" in msg

    def test_no_server_channel_does_not_broadcast(self, reset_autosave_started):
        # No exception when server channel is None
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            # Should not raise
            autosave_mod.autosave_tick()

    def test_exception_in_save_objects_caught(self, reset_autosave_started):
        # INTENT: a failure in save_objects should not propagate
        with patch("atheriz.globals.autosave.save_objects", side_effect=RuntimeError("db down")), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            # Should not raise
            autosave_mod.autosave_tick()

    def test_exception_in_map_handler_caught(self, reset_autosave_started):
        with patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler", side_effect=RuntimeError("map err")), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            # Should not raise
            autosave_mod.autosave_tick()

    def test_failure_message_to_server_channel(self, reset_autosave_started):
        # INTENT: when autosave fails, server channel gets a failure message
        mock_channel = MagicMock()
        with patch("atheriz.globals.autosave.save_objects", side_effect=RuntimeError("db down")), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=mock_channel):
            autosave_mod.autosave_tick()
        # The channel got a failure message
        calls = [c.args[0] for c in mock_channel.msg.call_args_list]
        assert any("Autosave failed" in m for m in calls)

    def test_explicit_failure_does_not_preceed_success(self, reset_autosave_started):
        # INTENT: when autosave fails, no success message is broadcast
        mock_channel = MagicMock()
        with patch("atheriz.globals.autosave.save_objects", side_effect=RuntimeError("db down")), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=mock_channel):
            autosave_mod.autosave_tick()
        for call in mock_channel.msg.call_args_list:
            msg = call.args[0]
            assert "Autosave completed" not in msg or "failed" in msg.lower()


class TestStartAutosave:
    def test_disabled_when_minutes_zero(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 0)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
        mock_ticker.add_coro.assert_not_called()
        assert autosave_mod._autosave_started is False

    def test_starts_when_minutes_set(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
        mock_ticker.add_coro.assert_called_once()
        # First positional arg should be autosave_tick
        assert mock_ticker.add_coro.call_args.args[0] is autosave_mod.autosave_tick
        # Second should be the interval in seconds
        assert mock_ticker.add_coro.call_args.args[1] == 300.0
        assert autosave_mod._autosave_started is True

    def test_no_double_start(self, reset_autosave_started, monkeypatch):
        # INTENT: starting twice should not double-register the coro
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
            autosave_mod.start_autosave()
        # Only one call even though start was called twice
        mock_ticker.add_coro.assert_called_once()
        assert autosave_mod._autosave_started is True

    def test_minute_change_reflected(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 15)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
        assert mock_ticker.add_coro.call_args.args[1] == 900.0


class TestStopAutosave:
    def test_noop_when_not_started(self, reset_autosave_started):
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.stop_autosave()
        mock_ticker.remove_coro.assert_not_called()
        assert autosave_mod._autosave_started is False

    def test_stops_when_started(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
            assert autosave_mod._autosave_started is True
            autosave_mod.stop_autosave()
        mock_ticker.remove_coro.assert_called_once()
        assert autosave_mod._autosave_started is False

    def test_removes_with_correct_interval(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 10)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
            autosave_mod.stop_autosave()
        # remove_coro should have been called with the interval
        assert mock_ticker.remove_coro.call_args.args[1] == 600.0
        # And the coro
        assert mock_ticker.remove_coro.call_args.args[0] is autosave_mod.autosave_tick

    def test_can_restart_after_stop(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker):
            autosave_mod.start_autosave()
            autosave_mod.stop_autosave()
            # After stop, _autosave_started is False, so start should work again
            autosave_mod.start_autosave()
        assert mock_ticker.add_coro.call_count == 2
        assert autosave_mod._autosave_started is True


class TestAutosaveIntegration:
    def test_full_cycle(self, reset_autosave_started, monkeypatch):
        monkeypatch.setattr(settings, "AUTOSAVE_MINUTES", 5)
        mock_ticker = MagicMock()
        with patch("atheriz.globals.autosave.get_async_ticker", return_value=mock_ticker), \
             patch("atheriz.globals.autosave.save_objects"), \
             patch("atheriz.globals.autosave.get_map_handler"), \
             patch("atheriz.globals.autosave.get_node_handler"), \
             patch("atheriz.globals.autosave.get_server_channel", return_value=None):
            # Start
            autosave_mod.start_autosave()
            # Tick (simulate the ticker firing it)
            autosave_mod.autosave_tick()
            # Stop
            autosave_mod.stop_autosave()
        mock_ticker.add_coro.assert_called_once()
        mock_ticker.remove_coro.assert_called_once()

    def test_autosave_module_state_isolated(self, reset_autosave_started):
        # The _autosave_started global should be resettable
        autosave_mod._autosave_started = True
        assert autosave_mod._autosave_started is True
        # Fixture will reset
