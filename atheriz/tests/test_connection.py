"""Tests for atheriz.network.connection — BaseConnection interface."""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from atheriz.network.connection import BaseConnection
from atheriz.objects.session import Session
from atheriz.tests.fakes import FakeConnection


class ConcreteConn(BaseConnection):
    """Concrete subclass for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent = []
        self.closed = False

    def send_command(self, cmd, *args, **kwargs):
        self.sent.append((cmd, args, kwargs))

    def close(self):
        self.closed = True


class TestInit:
    def test_sets_session_id(self, global_test_env):
        c = ConcreteConn(session_id="abc")
        assert c.session_id == "abc"

    def test_session_id_none_default(self, global_test_env):
        c = ConcreteConn()
        assert c.session_id is None

    def test_creates_session(self, global_test_env):
        c = ConcreteConn()
        assert isinstance(c.session, Session)

    def test_session_links_to_connection(self, global_test_env):
        c = ConcreteConn()
        assert c.session.connection is c

    def test_initializes_loop(self, global_test_env):
        c = ConcreteConn()
        assert c.loop is not None

    def test_records_thread_id(self, global_test_env):
        c = ConcreteConn()
        assert c.thread_id == threading.get_ident()

    def test_lock_is_rlock(self, global_test_env):
        c = ConcreteConn()
        assert isinstance(c.lock, type(threading.RLock()))

    def test_failed_login_attempts_starts_zero(self, global_test_env):
        c = ConcreteConn()
        assert c.failed_login_attempts == 0


class TestSendCommand:
    def test_not_implemented_in_base(self, global_test_env):
        # INTENT: subclasses must override
        c = BaseConnection()
        with pytest.raises(NotImplementedError):
            c.send_command("text", "hello")


class TestClose:
    def test_not_implemented_in_base(self, global_test_env):
        c = BaseConnection()
        with pytest.raises(NotImplementedError):
            c.close()


class TestMsg:
    def test_no_args_no_kwargs_noop(self, global_test_env):
        c = ConcreteConn()
        c.msg()
        assert c.sent == []

    def test_simple_text(self, global_test_env):
        c = ConcreteConn()
        c.msg("hello")
        assert len(c.sent) == 1
        cmd, args, kwargs = c.sent[0]
        assert cmd == "text"
        assert "hello" in args[0]
        # Newline added
        assert args[0].endswith("\r\n")

    def test_text_with_screenreader_strips_ansi(self, global_test_env):
        c = ConcreteConn()
        c.session.screenreader = True
        c.msg("\x1b[31mred\x1b[0m")
        # ANSI is stripped
        assert "\x1b" not in c.sent[0][1][0]

    def test_text_without_screenreader_keeps_ansi(self, global_test_env):
        c = ConcreteConn()
        c.session.screenreader = False
        c.msg("\x1b[31mred\x1b[0m")
        # ANSI is preserved
        assert "\x1b" in c.sent[0][1][0]

    def test_text_kwarg(self, global_test_env):
        c = ConcreteConn()
        c.msg(text="hi")
        cmd, args, kwargs = c.sent[0]
        assert cmd == "text"
        assert "hi" in args[0]

    def test_non_text_kwarg_becomes_command(self, global_test_env):
        c = ConcreteConn()
        c.msg(prompt="> ")
        cmd, args, kwargs = c.sent[0]
        assert cmd == "prompt"
        assert args[0] == "> "

    def test_non_text_kwarg_with_text(self, global_test_env):
        # INTENT: when both text= and other kwargs are present, text is the message
        # and the other kwarg is preserved as a kwarg to send_command
        c = ConcreteConn()
        c.msg(text="hello", prompt="> ")
        cmd, args, kwargs = c.sent[0]
        # cmd remains "text" because the text branch was taken
        assert cmd == "text"
        assert "hello" in args[0]
        # The prompt kwarg is preserved
        assert kwargs.get("prompt") == "> "

    def test_text_then_positional(self, global_test_env):
        c = ConcreteConn()
        c.msg("hello", "world")
        # First arg gets \r\n appended
        cmd, args, _ = c.sent[0]
        assert cmd == "text"
        assert args[0].endswith("\r\n")
        assert "hello" in args[0]


class TestFakeConnectionFromFakes:
    """Verify the FakeConnection in fakes.py works as a BaseConnection."""

    def test_fake_inherits_base(self, global_test_env):
        from atheriz.tests.fakes import FakeConnection
        fc = FakeConnection()
        assert isinstance(fc, BaseConnection)

    def test_fake_records_msgs(self, global_test_env):
        from atheriz.tests.fakes import FakeConnection
        fc = FakeConnection()
        fc.msg("hello")
        assert len(fc.sent) == 1
        # The sent tuple is (cmd, args, kwargs)
        assert fc.sent[0][0] == "text"
        assert "hello" in fc.sent[0][1][0]

    def test_fake_close(self, global_test_env):
        from atheriz.tests.fakes import FakeConnection
        fc = FakeConnection()
        fc.close()
        assert fc.closed is True


class TestIntegration:
    def test_connection_lifecycle(self, global_test_env):
        c = ConcreteConn(session_id="test")
        c.msg("Welcome!")
        assert len(c.sent) == 1
        c.close()
        assert c.closed is True

    def test_multiple_msgs(self, global_test_env):
        c = ConcreteConn()
        c.msg("one")
        c.msg("two")
        c.msg("three")
        assert len(c.sent) == 3
        # Each had a newline added
        for cmd, args, kwargs in c.sent:
            assert args[0].endswith("\r\n")
