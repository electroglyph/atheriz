import asyncio
from unittest.mock import MagicMock
from atheriz.objects.base_account import Account
from atheriz.objects.base_obj import Object
from atheriz.objects.session import Session
from atheriz.commands.unloggedin.connect import char_selection

def test_double_puppet_race(global_test_env, fixed_salt):
    account = Account.create("alice", "secret")
    char = Object.create(None, "Hob", is_pc=True)
    account.add_character(char)
    assert char.session is None
    session1 = Session(account=account, connection=MagicMock())
    session1.puppet = None
    caller1 = MagicMock()
    caller1.session = session1
    caller1.msg = MagicMock()
    session2 = Session(account=account, connection=MagicMock())
    session2.puppet = None
    caller2 = MagicMock()
    caller2.session = session2
    caller2.msg = MagicMock()
    async def prompt1(text):
        await asyncio.sleep(0.05)
        return "0"
    async def prompt2(text):
        await asyncio.sleep(0.05)
        return "0"
    session1.prompt = prompt1
    session2.prompt = prompt2
    async def run_both():
        t1 = asyncio.create_task(char_selection(caller1, account))
        t2 = asyncio.create_task(char_selection(caller2, account))
        done, pending = await asyncio.wait([t1, t2], timeout=3)
        for p in pending:
            p.cancel()
            try:
                await p
            except asyncio.CancelledError:
                pass
        return t1, t2
    asyncio.run(run_both())
    success = sum(1 for s in [session1, session2] if s.puppet is char)
    assert success == 1, f"expected 1 success got {success}"
    loser = caller1 if session1.puppet is not char else caller2
    msgs = " ".join(str(c.args[0]) for c in loser.msg.call_args_list)
    assert "not available" in msgs.lower()
    winner = session1 if session1.puppet is char else session2
    assert char.session is winner

def test_already_puppeted_direct(global_test_env, fixed_salt):
    account = Account.create("bob", "secret2")
    char = Object.create(None, "BobChar", is_pc=True)
    account.add_character(char)
    sess1 = Session(account=account, connection=MagicMock())
    sess1.puppet = char
    char.session = sess1
    sess2 = Session(account=account, connection=MagicMock())
    sess2.puppet = None
    caller2 = MagicMock()
    caller2.session = sess2
    caller2.msg = MagicMock()
    async def prompt(text):
        return "0"
    sess2.prompt = prompt
    async def run():
        task = asyncio.create_task(char_selection(caller2, account))
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
    assert sess2.puppet is None
    msgs = " ".join(str(c.args[0]) for c in caller2.msg.call_args_list)
    assert "not available" in msgs.lower()
    assert char.session is sess1

def test_wiring_atomic(global_test_env, fixed_salt):
    account = Account.create("carol", "secret3")
    char = Object.create(None, "CarolChar", is_pc=True)
    account.add_character(char)
    sess = Session(account=account, connection=MagicMock())
    sess.puppet = None
    caller = MagicMock()
    caller.session = sess
    caller.msg = MagicMock()
    async def prompt(text):
        return "0"
    sess.prompt = prompt
    asyncio.run(char_selection(caller, account))
    assert sess.puppet is char
    assert char.session is sess
