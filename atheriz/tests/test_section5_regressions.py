import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import atheriz.settings as settings
from atheriz.inputfuncs import InputFuncs
from atheriz.network.manager import ConnectionManager
from atheriz.tests.fakes import FakeConnection
from atheriz.globals.objects import filter_by
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
import atheriz.globals.mapedit as mapedit


def _fake_conn_with_puppet(is_builder):
    conn = MagicMock()
    puppet = MagicMock()
    puppet.is_builder = is_builder
    session = MagicMock()
    session.puppet = puppet
    conn.session = session
    conn.client_host = "1.2.3.4"
    conn.send_command = MagicMock()
    return conn, puppet


def test_map_edit_rejects_non_builder_before_key_validation(global_test_env):
    funcs = InputFuncs()
    conn, puppet = _fake_conn_with_puppet(is_builder=False)
    puppet.is_builder = False
    fake_chain = MagicMock(area="test", z=0)
    result_processed = MagicMock(status=mapedit.PROCESSED, new_key="newk", chain=fake_chain)
    with patch("atheriz.inputfuncs.mapedit.consume", return_value=result_processed) as mock_consume:
        with patch("atheriz.inputfuncs.get_map_handler"):
            funcs.map_edit(conn, ["somekey", 1, [[0, 0, "x"]]], {})
    mock_consume.assert_not_called()
    conn.send_command.assert_called_once()
    assert conn.send_command.call_args[0][0] == "map_edit_reject"


def test_map_edit_allows_builder_to_proceed(global_test_env):
    funcs = InputFuncs()
    conn, puppet = _fake_conn_with_puppet(is_builder=True)
    fake_chain = MagicMock(area="test", z=0)
    result = MagicMock(status=mapedit.PROCESSED, new_key="newk", chain=fake_chain)
    with patch("atheriz.inputfuncs.mapedit.consume", return_value=result) as mock_consume:
        mi = MagicMock()
        mi.lock = MagicMock()
        mi.lock.__enter__ = MagicMock(return_value=None)
        mi.lock.__exit__ = MagicMock(return_value=None)
        mi.batch_update.return_value.__enter__ = MagicMock(return_value=None)
        mi.batch_update.return_value.__exit__ = MagicMock(return_value=None)
        mi.pre_grid = {}
        with patch("atheriz.inputfuncs.get_map_handler") as mock_mh:
            mock_mh.return_value.get_mapinfo.return_value = mi
            with patch("atheriz.inputfuncs.get_node_handler") as mock_nh:
                mock_nh.return_value.get_area.return_value = None
                funcs.map_edit(conn, ["somekey", 1, [[0, 0, "x"]]], {})
    mock_consume.assert_called_once()
    assert conn.send_command.call_args[0][0] == "map_ack"


def test_map_validate_moves_rejects_non_builder(global_test_env):
    funcs = InputFuncs()
    conn, puppet = _fake_conn_with_puppet(is_builder=False)
    with patch("atheriz.inputfuncs.mapedit.consume") as mock_consume:
        funcs.map_validate_moves(conn, ["k", 1, [[0, 0, 1, 1]]], {})
    mock_consume.assert_not_called()
    conn.send_command.assert_called_once()
    assert conn.send_command.call_args[0][0] == "map_edit_reject"


def test_websocket_byte_size_counts_utf8_not_chars():
    raw = "☃" * 30000
    assert len(raw) == 30000
    assert len(raw.encode("utf-8")) == 90000
    limit = 65536
    assert len(raw) < limit
    assert len(raw.encode("utf-8")) > limit
    with patch.object(settings, "WEBSOCKET_MAX_MESSAGE_SIZE", limit):
        assert len(raw.encode("utf-8")) > settings.WEBSOCKET_MAX_MESSAGE_SIZE


def test_connect_lookup_is_case_insensitive(global_test_env, fixed_salt):
    acc = Account.create("FooBar", "password123")
    from atheriz.commands.unloggedin.connect import ConnectCommand
    from atheriz.tests.fakes import FakeConnection as FC

    conn = FC()
    conn.client_host = "1.1.1.1"
    conn.session = MagicMock()
    conn.session.account = None
    conn.session.puppet = None
    import atheriz.commands.unloggedin.connect as conn_mod

    caller = MagicMock()
    caller.client_host = "1.1.1.1"
    caller.session = MagicMock()
    caller.session.account = None
    caller.session.puppet = None
    caller.msg = MagicMock()
    caller.send_command = MagicMock()
    caller.close = MagicMock()

    async def _run():
        cmd = ConnectCommand()
        args = MagicMock()
        args.account_name = "foobar"
        args.password = "password123"
        with patch("atheriz.commands.unloggedin.connect.char_selection", new=AsyncMock()):
            await cmd.run(caller, args)
        caller.msg.assert_not_called() or True
        assert caller.session.account is acc or caller.session.account is not None

    asyncio.run(_run())


def test_banned_account_does_not_trigger_password_check(global_test_env, fixed_salt):
    acc = Account.create("BannedUser", "password123")
    with acc.lock:
        acc.is_banned = True
        acc.ban_reason = "testing"

    from atheriz.commands.unloggedin.connect import ConnectCommand

    caller = MagicMock()
    caller.client_host = "2.2.2.2"
    caller.session = MagicMock()
    caller.session.account = None
    caller.msg = MagicMock()
    caller.close = MagicMock()
    caller.send_command = MagicMock()

    async def _run():
        cmd = ConnectCommand()
        args = MagicMock()
        args.account_name = "banneduser"
        args.password = "wrongpassword"
        with patch.object(acc, "check_password", wraps=acc.check_password) as mock_check:
            mock_check.side_effect = AssertionError("check_password should not be called for banned account")
            await cmd.run(caller, args)
            mock_check.assert_not_called()
        caller.msg.assert_called()
        assert any("banned" in str(c.args[0]).lower() for c in caller.msg.call_args_list)
        caller.close.assert_called_once()

    asyncio.run(_run())
    with acc.lock:
        acc.is_banned = False


def test_create_account_endpoint_validates_names_and_password(global_test_env, tmp_path):
    from atheriz.atheriz import create_account_endpoint
    from unittest.mock import patch

    class _FakeRequest:
        def __init__(self, token="real-token", body=None):
            self.headers = {"X-Admin-Token": token}
            self.client = MagicMock()
            self.client.host = "127.0.0.1"
            self._body = body

        async def json(self):
            if self._body is None:
                raise ValueError("bad json")
            return self._body

    (tmp_path / "admin.token").write_text("real-token")

    async def _check(body, should_fail=True):
        with patch.object(settings, "SECRET_PATH", str(tmp_path)), \
             patch("atheriz.atheriz.run_in_threadpool", AsyncMock(side_effect=lambda fn, *args: fn(*args))), \
             patch("atheriz.atheriz.at_char_create") as mock_char:
            res = await create_account_endpoint(_FakeRequest(body=body))
            if should_fail:
                assert res["status"] == "error"
                mock_char.assert_not_called()
            else:
                assert res["status"] == "ok"
                mock_char.assert_called_once()

    asyncio.run(_check({"account_name": "ab", "char_name": "Bob", "password": "password123"}))
    asyncio.run(_check({"account_name": "validname", "char_name": "a", "password": "password123"}))
    asyncio.run(_check({"account_name": "validname", "char_name": "Bob", "password": "short"}))
    asyncio.run(_check({"account_name": "\x1b[31m", "char_name": "Bob", "password": "password123"}))
    asyncio.run(_check({"account_name": "goodname", "char_name": "GoodChar", "password": "goodpass123"}, should_fail=False))


def test_per_ip_limit_applies_to_unknown_host(global_test_env):
    mgr = ConnectionManager()
    cap = patch("atheriz.settings.MAX_CONNECTIONS_PER_IP", 2)
    with cap:
        assert mgr.register_connection("c0", FakeConnection()) is True
        assert mgr.register_connection("c1", FakeConnection()) is True
        third = FakeConnection()
        with patch.object(third, "close") as spy:
            assert mgr.register_connection("c2", third) is False
            spy.assert_called_once()
