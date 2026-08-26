import pytest
from atheriz.utils import Coord
from unittest.mock import MagicMock, patch
from argparse import Namespace

from atheriz import settings
from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_obj import Object
from atheriz.commands.loggedin.socials import CmdSocials, SOCIALS_DICT

@pytest.fixture
def test_env():
    handler = NodeHandler()
    area = NodeArea(name="TestAreaSocials")
    grid = NodeGrid(z=0)
    
    room = Node(coord=Coord("TestAreaSocials", 0, 0, 0))
    grid.add_node(room)
    area.add_grid(grid)
    handler.add_area(area)

    alice = Object.create(None, "Alice", is_pc=True)
    bob = Object.create(None, "Bob", is_pc=True)
    
    alice.location = room
    bob.location = room
    
    room.add_object(alice)
    room.add_object(bob)
    
    alice.msg = MagicMock()
    bob.msg = MagicMock()
    
    yield room, alice, bob
    
    # cleanup
    try:
        room.remove_object(alice)
        room.remove_object(bob)
    except:
        pass


def test_untargeted_social(test_env):
    room, alice, bob = test_env
    cmd = CmdSocials()
    
    args = Namespace(cmdstring="smile", target=[])
    cmd.run(alice, args)
    
    assert alice.msg.called
    alice_args, alice_kwargs = alice.msg.call_args
    alice_text = alice_args[0] if alice_args else alice_kwargs.get('text', '')
    if isinstance(alice_text, tuple): alice_text = alice_text[0]
    
    assert "You smile." in alice_text
    
    assert bob.msg.called
    bob_args, bob_kwargs = bob.msg.call_args
    bob_text = bob_args[0] if bob_args else bob_kwargs.get('text', '')
    if isinstance(bob_text, tuple): bob_text = bob_text[0]
    
    assert "Alice (offline) smiles." in bob_text


def test_targeted_social(test_env):
    room, alice, bob = test_env
    cmd = CmdSocials()
    
    alice.search = MagicMock(return_value=[bob])
    
    args = Namespace(cmdstring="hug", target=["Bob"])
    cmd.run(alice, args)
    
    assert alice.msg.called
    alice_args, alice_kwargs = alice.msg.call_args
    alice_text = alice_args[0] if alice_args else alice_kwargs.get('text', '')
    if isinstance(alice_text, tuple): alice_text = alice_text[0]
    
    assert "You hug Bob (offline)." in alice_text
    
    assert bob.msg.called
    bob_args, bob_kwargs = bob.msg.call_args
    bob_text = bob_args[0] if bob_args else bob_kwargs.get('text', '')
    if isinstance(bob_text, tuple): bob_text = bob_text[0]
    
    assert "Alice (offline) hugs you." in bob_text


def test_targeted_social_multiple_matches(test_env):
    """search returns a list; ambiguous target must error, not pick first silently."""
    room, alice, bob = test_env
    cmd = CmdSocials()

    alice.search = MagicMock(return_value=[bob, alice])

    args = Namespace(cmdstring="hug", target=["Bob"])
    cmd.run(alice, args)

    # fixed M-35: ambiguous should report multiple matches
    all_msgs = " ".join(str(c.args[0]) for c in alice.msg.call_args_list if c.args)
    assert "multiple" in all_msgs.lower()
    assert not bob.msg.called

def test_missing_target_social(test_env):
    room, alice, bob = test_env
    cmd = CmdSocials()

    alice.search = MagicMock(return_value=None)

    args = Namespace(cmdstring="hug", target=["Charlie"])
    cmd.run(alice, args)

    assert alice.msg.called
    assert not bob.msg.called
    msg = alice.msg.call_args[0][0] if alice.msg.call_args[0] else ""
    assert "Could not find" in msg


def _make_caller(name="Alice", builder=False, screenreader=False, term_width=80):
    c = MagicMock(spec=Object)
    c.name = name
    c.id = 1
    c.privilege_level = settings.Privilege.Builder if builder else settings.Privilege.Player
    c.quelled = False
    c.no_follow = False
    c.following = None
    c.followers = set()
    c.group_channel = None
    c.session = MagicMock()
    c.session.screenreader = screenreader
    c.session.term_width = term_width
    c.msg = MagicMock()
    c.location = None
    c.contents = []
    return c


class TestCmdSocialsExtra:
    def test_socials_command_lists_aliases(self):
        c = _make_caller()
        args = Namespace(cmdstring="socials", target=[])
        CmdSocials().run(c, args)
        c.msg.assert_called_once()
        text = c.msg.call_args[0][0]
        assert "smile" in text
        assert "hug" in text

    def test_unknown_cmdstring_uses_invocation_msg(self):
        c = _make_caller()
        c.location = MagicMock()
        c.location.msg_contents = MagicMock()
        args = Namespace(cmdstring="laugh", target=[])
        CmdSocials().run(c, args)
        c.location.msg_contents.assert_called_once()

    def test_all_socials_have_two_templates(self):
        for verb, templates in SOCIALS_DICT.items():
            assert isinstance(templates, tuple), f"{verb} not tuple"
            assert len(templates) == 2, f"{verb} does not have 2 templates"
            assert "$You" in templates[0]
            assert "$You" in templates[1]

    def test_targeted_social_template_is_used(self):
        c = _make_caller()
        target = MagicMock()
        target.id = 99
        target.is_pc = True
        target.is_npc = False
        c.search = MagicMock(return_value=[target])
        c.location = MagicMock()
        c.location.msg_contents = MagicMock()
        args = Namespace(cmdstring="wave", target=["Bob"])
        CmdSocials().run(c, args)
        c.location.msg_contents.assert_called_once()
        kwargs = c.location.msg_contents.call_args.kwargs
        assert "target" in kwargs["mapping"]
        assert kwargs["mapping"]["target"] is target


class TestSocialMultipleTargetsShouldError:
    def test_social_with_multiple_matching_targets_should_error(self, global_test_env):
        caller = _make_caller()
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        bob1 = MagicMock()
        bob1.name = "Bob"
        bob1.id = 1
        bob2 = MagicMock()
        bob2.name = "Bob"
        bob2.id = 2
        caller.search = MagicMock(return_value=[bob1, bob2])
        args = Namespace(cmdstring="hug", target=["Bob"])
        CmdSocials().run(caller, args)
        caller.msg.assert_called()
        all_msgs = " ".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        assert "multiple" in all_msgs.lower(), "social with ambiguous target should report multiple matches, not silently pick first"
        caller.location.msg_contents.assert_not_called()

    def test_social_ambiguous_target_does_not_hug_first(self):
        caller = _make_caller()
        caller.location = MagicMock()
        caller.location.msg_contents = MagicMock()
        a = MagicMock()
        a.name = "Alex"
        a.id = 10
        b = MagicMock()
        b.name = "Alex"
        b.id = 11
        caller.search = MagicMock(return_value=[a, b])
        args = Namespace(cmdstring="smile", target=["Alex"])
        CmdSocials().run(caller, args)
        assert caller.location.msg_contents.call_count == 0
        assert any("multiple" in str(c.args[0]).lower() for c in caller.msg.call_args_list if c.args)
