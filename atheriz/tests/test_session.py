"""Tests for atheriz.objects.session — Session lifecycle and prompt coroutine."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from atheriz import settings
from atheriz.objects.base_obj import Object
from atheriz.objects.session import Session
from atheriz.tests.fakes import make_object


class TestSessionConstructor:
    def test_defaults(self, global_test_env):
        s = Session()
        assert s.account is None
        assert s.connection is None
        assert s.last_puppet is None
        assert s.puppet is None
        assert s.term_width == settings.CLIENT_DEFAULT_WIDTH
        assert s.term_height == settings.CLIENT_DEFAULT_HEIGHT
        assert s.map_width == 0
        assert s.map_height == 0
        assert s.screenreader is False
        assert s.conn_time == 0.0
        assert not hasattr(s, "cmd_last")
        assert not hasattr(s, "cmd_total")
        assert not hasattr(s, "last_cmd")
        assert s.input_future is None

    def test_with_account_and_connection(self, global_test_env):
        acc = make_object("alice", is_account=True)
        conn = MagicMock()
        s = Session(account=acc, connection=conn)
        assert s.account is acc
        assert s.connection is conn

    def test_width_height_come_from_settings(self, global_test_env):
        s = Session()
        assert s.term_width == 78  # CLIENT_DEFAULT_WIDTH
        assert s.term_height == 45  # CLIENT_DEFAULT_HEIGHT


class TestAtConnect:
    def test_sets_conn_time(self, global_test_env):
        s = Session()
        assert s.conn_time == 0.0
        before = time.time()
        s.at_connect()
        after = time.time()
        assert before <= s.conn_time <= after

    def test_overwrites_conn_time(self, global_test_env):
        s = Session()
        s.at_connect()
        first = s.conn_time
        time.sleep(0.001)
        s.at_connect()
        assert s.conn_time >= first


class TestAtDisconnect:
    def test_no_puppet_no_account(self, global_test_env):
        s = Session()
        # Should not raise
        s.at_disconnect()

    def test_puppet_at_disconnect_called(self, global_test_env):
        puppet = make_object("char1", is_pc=True)
        s = Session()
        s.puppet = puppet
        s.at_disconnect()
        # at_disconnect default for Object is a no-op but should not raise
        # If we mock it we can assert
        puppet.at_disconnect = MagicMock()
        s.at_disconnect()
        puppet.at_disconnect.assert_called_once()

    def test_puppet_seconds_played_incremented(self, global_test_env):
        puppet = make_object("char1", is_pc=True)
        s = Session()
        s.puppet = puppet
        s.conn_time = time.time() - 5.0
        s.at_disconnect()
        # seconds_played should have grown by ~5 (within tolerance)
        assert puppet.seconds_played >= 4.5
        assert puppet.seconds_played < 6.0

    def test_account_at_disconnect_called(self, global_test_env):
        acc = make_object("alice", is_account=True)
        s = Session()
        s.account = acc
        acc.at_disconnect = MagicMock()
        s.at_disconnect()
        acc.at_disconnect.assert_called_once()

    def test_both_puppet_and_account(self, global_test_env):
        puppet = make_object("char1", is_pc=True)
        acc = make_object("alice", is_account=True)
        s = Session(account=acc)
        s.puppet = puppet
        puppet.at_disconnect = MagicMock()
        acc.at_disconnect = MagicMock()
        s.at_disconnect()
        puppet.at_disconnect.assert_called_once()
        acc.at_disconnect.assert_called_once()

    def test_seconds_played_persists(self, global_test_env):
        puppet = make_object("char1", is_pc=True)
        s = Session()
        s.puppet = puppet
        s.conn_time = time.time() - 2.0
        s.at_disconnect()
        first = puppet.seconds_played
        s.puppet = puppet
        s.conn_time = time.time() - 3.0
        s.at_disconnect()
        assert puppet.seconds_played > first

    def test_at_disconnect_cancels_pending_input_future(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)

        async def run():
            task = asyncio.create_task(s.prompt("> "))
            await asyncio.sleep(0)
            assert s.input_future is not None
            assert not s.input_future.done()
            fut = s.input_future
            s.at_disconnect()
            for _ in range(100):
                if fut.cancelled():
                    break
                await asyncio.sleep(0.01)
            assert fut.cancelled()
            assert s.input_future is None

        asyncio.run(run())


class TestMsg:
    def test_msg_proxies_to_connection(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)
        s.msg("hello")
        conn.msg.assert_called_once_with("hello")

    def test_msg_with_kwargs(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)
        s.msg("hi", prompt=">", foo="bar")
        conn.msg.assert_called_once_with("hi", prompt=">", foo="bar")

    def test_msg_no_connection_raises(self, global_test_env):
        s = Session()
        with pytest.raises(AttributeError):
            s.msg("hi")


class TestPrompt:
    def test_prompt_round_trip(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)

        async def run():
            task = asyncio.create_task(s.prompt("> "))
            # Let the coroutine reach the await
            await asyncio.sleep(0)
            s.input_future.set_result("hello")
            return await task

        result = asyncio.run(run())
        assert result == "hello"
        # The prompt was sent via msg
        conn.msg.assert_called_with("> ")

    def test_prompt_sends_text_via_msg(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)

        async def run():
            task = asyncio.create_task(s.prompt("> "))
            await asyncio.sleep(0)
            s.input_future.set_result("bob")
            return await task

        asyncio.run(run())
        conn.msg.assert_called_with("> ")

    def test_prompt_creates_new_input_future(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)

        async def run():
            task = asyncio.create_task(s.prompt("> "))
            await asyncio.sleep(0)
            assert s.input_future is not None
            assert not s.input_future.done()
            s.input_future.set_result("ok")
            return await task

        asyncio.run(run())

    def test_prompt_with_empty_response(self, global_test_env):
        conn = MagicMock()
        s = Session(connection=conn)

        async def run():
            task = asyncio.create_task(s.prompt("> "))
            await asyncio.sleep(0)
            s.input_future.set_result("")
            return await task

        assert asyncio.run(run()) == ""

    def test_prompt_msg_called_before_future_created(self, global_test_env):
        # The order of operations in prompt() is: msg(text); future = ...; await future
        # After awaiting, msg should have been called.
        conn = MagicMock()
        s = Session(connection=conn)

        async def run():
            task = asyncio.create_task(s.prompt("> "))
            await asyncio.sleep(0)
            s.input_future.set_result("x")
            return await task

        asyncio.run(run())
        # msg was called with the prompt text
        assert conn.msg.call_args[0] == ("> ",)


def test_session_prompt_binds_future_to_existing_loop(global_test_env):
    loop = asyncio.new_event_loop()
    conn = MagicMock()
    conn.loop = loop
    conn.send_command = MagicMock()
    conn.msg = MagicMock()
    sess = Session(connection=conn)

    async def run_prompt():
        with patch("atheriz.objects.session.asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            coro = sess.prompt("hello")
            with patch("atheriz.globals.get.get_async_threadpool") as mock_gtp:
                mock_pool = MagicMock()
                mock_pool.loop = loop
                mock_gtp.return_value = mock_pool
                task = loop.create_task(coro)
                await asyncio.sleep(0.05)
                fut = sess.input_future
                assert fut is not None
                try:
                    fut_loop = fut.get_loop()
                except RuntimeError:
                    fut_loop = None
                assert fut_loop is loop, f"future bound to {fut_loop} not {loop}"
                if not fut.done():
                    fut.set_result("answer")
                try:
                    result = await asyncio.wait_for(task, timeout=1)
                    assert result == "answer"
                except asyncio.TimeoutError:
                    task.cancel()
                    raise

    try:
        loop.run_until_complete(run_prompt())
    finally:
        loop.close()


def test_session_echo_race_masked_prompt_then_disconnect_sends_echo_on(global_test_env):
    loop = asyncio.new_event_loop()
    conn = MagicMock()
    conn.loop = loop
    conn.send_command = MagicMock()
    conn.msg = MagicMock()
    sess = Session(connection=conn)
    async def run():
        task = asyncio.create_task(sess.prompt("secret", mask=True))
        await asyncio.sleep(0)
        assert sess._input_masked is True
        assert sess.input_future is not None
        sess.at_disconnect()
        conn.send_command.assert_any_call("echo_on")
        assert sess._input_masked is False
        assert sess.input_future is None
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    loop.run_until_complete(run())
    loop.close()

def test_session_double_disconnect_idempotent(global_test_env):
    conn = MagicMock()
    conn.send_command = MagicMock()
    sess = Session(connection=conn)
    sess.puppet = MagicMock()
    sess.puppet.session = conn
    sess.puppet.at_disconnect = MagicMock()
    sess.at_disconnect()
    first_calls = sess.puppet.at_disconnect.call_count
    sess.at_disconnect()
    assert sess.puppet is None or sess.puppet.at_disconnect.call_count == first_calls, "second disconnect must not double-call puppet"

def test_session_echo_state_not_leaked_on_cancelled_prompt(global_test_env):
    loop = asyncio.new_event_loop()
    conn = MagicMock()
    conn.loop = loop
    conn.send_command = MagicMock()
    conn.msg = MagicMock()
    sess = Session(connection=conn)
    async def run():
        t1 = asyncio.create_task(sess.prompt("first", mask=True))
        await asyncio.sleep(0)
        assert sess._input_masked is True
        t2 = asyncio.create_task(sess.prompt("second", mask=False))
        await asyncio.sleep(0)
        assert sess._input_masked is False
        conn.send_command.assert_any_call("echo_on")
        for t in (t1, t2):
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
    loop.run_until_complete(run())
    loop.close()

def test_connection_double_close_no_runtime_error(global_test_env):
    from atheriz.tests.fakes import FakeConnection
    conn = FakeConnection()
    conn.close()
    try:
        conn.close()
    except RuntimeError as e:
        assert False, f"double close raised RuntimeError: {e}"
    assert conn.closed is True
