import threading
from unittest.mock import MagicMock, patch

import pytest

from atheriz.objects.base_obj import Object
from atheriz.server_events import at_char_create


@pytest.fixture
def real_home_node():
    from atheriz.objects.nodes import Node, Coord
    from atheriz.globals.objects import add_object
    from atheriz.globals.get import get_unique_id

    home_coord = Coord("limbo", 0, 0, 0)
    home = Node(coord=home_coord, desc="Home", theme="limbo", symbol="#")
    home.id = get_unique_id()
    add_object(home)

    nh = MagicMock()
    nh.get_node.return_value = home
    with patch("atheriz.server_events.get_node_handler", return_value=nh):
        yield home


def test_character_creation_respects_max_under_concurrency(global_test_env, real_home_node, fixed_salt):
    from atheriz.objects.base_account import Account
    from atheriz.globals.objects import filter_by
    import atheriz.settings as settings

    orig_max = settings.MAX_CHARACTERS
    settings.MAX_CHARACTERS = 3
    try:
        acct = Account.create("alice", "password123")
        assert acct is not None

        # Use distinct character names to avoid name collision handling
        names = [f"Hero{i}" for i in range(10)]

        def create_one(name):
            at_char_create("alice", name, "password123")

        threads = [threading.Thread(target=create_one, args=(n,)) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)
            assert not t.is_alive(), "deadlock in at_char_create"

        # No more than MAX characters on account
        assert len(acct.characters) == settings.MAX_CHARACTERS

        # No orphan PCs beyond those linked to account
        pcs = filter_by(lambda x: getattr(x, "is_pc", False) and getattr(x, "name", "").startswith("Hero"))
        # pcs includes only the characters that were successfully linked; orphans would be extra
        assert len(pcs) == settings.MAX_CHARACTERS, f"orphan PCs leaked: {len(pcs)} vs {len(acct.characters)}"

        # IDs not leaked beyond needed: check that no extra Hero objects exist beyond account list
        linked_ids = set(acct.characters)
        for pc in pcs:
            assert pc.id in linked_ids
    finally:
        settings.MAX_CHARACTERS = orig_max


def test_character_creation_does_not_leak_id_on_overflow(global_test_env, real_home_node, fixed_salt):
    from atheriz.objects.base_account import Account
    from atheriz.globals.get import get_id
    import atheriz.settings as settings

    orig_max = settings.MAX_CHARACTERS
    settings.MAX_CHARACTERS = 2
    try:
        acct = Account.create("bob", "password123")
        acct.characters = list(range(settings.MAX_CHARACTERS))  # fill with dummy ids

        before_id = get_id()

        with patch("atheriz.server_events.save_objects"):
            at_char_create("bob", "Overflow", "password123")

        after_id = get_id()
        # With fix, no Object.create should have been called, so global ID not incremented
        assert after_id == before_id, f"ID leaked: {before_id} -> {after_id}"

        assert len(acct.characters) == settings.MAX_CHARACTERS
    finally:
        settings.MAX_CHARACTERS = orig_max


def test_character_creation_single_thread_still_works(global_test_env, real_home_node, fixed_salt):
    from atheriz.objects.base_account import Account
    from atheriz.globals.objects import get

    acct = Account.create("carol", "password123")
    with patch("atheriz.server_events.save_objects"):
        at_char_create("carol", "NewHero", "password123")

    assert len(acct.characters) == 1
    char = get(acct.characters[0])[0]
    assert char.name == "NewHero"
    assert char.is_pc is True


def test_guest_is_temporary_removed_on_disconnect_no_leak(global_test_env):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from atheriz.commands.unloggedin.guest import GuestCommand
    from atheriz.globals.objects import _ALL_OBJECTS
    from atheriz.tests.fakes import FakeConnection
    from atheriz.objects.nodes import Node, Coord
    from atheriz.globals.objects import add_object
    from atheriz.globals.get import get_unique_id, get_node_handler
    import atheriz.settings as s
    orig = s.GUEST_ENABLED
    s.GUEST_ENABLED = True
    home_coord = Coord("limbo", 0, 0, 0)
    home = Node(coord=home_coord, desc="Home", symbol="#")
    home.id = get_unique_id()
    add_object(home)
    nh = get_node_handler()
    nh.get_node = MagicMock(return_value=home)
    try:
        conn = FakeConnection()
        caller = MagicMock()
        caller.session = conn.session
        caller.session.puppet = None
        caller.msg = MagicMock()
        caller.send_command = MagicMock()
        caller.client_host = "10.9.8.7"
        caller.session.prompt = AsyncMock(side_effect=["LeakGuest", "M", "desc"])
        before = set(_ALL_OBJECTS.keys())
        asyncio.run(GuestCommand().run(caller, None))
        guest = caller.session.puppet
        assert guest is not None and guest.is_temporary is True
        assert guest.id in _ALL_OBJECTS
        conn.session.at_disconnect()
        assert guest.id not in _ALL_OBJECTS, "guest temporary object leaked after disconnect"
        assert len(_ALL_OBJECTS) == len(before)
    finally:
        s.GUEST_ENABLED = orig
