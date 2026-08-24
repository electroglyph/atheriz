"""Issue tests: `at_post_puppet` re-moves the puppet to its current location
with announcement enabled, broadcasting "walks in."/"walks away." to the room
on every login/puppet.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from atheriz import settings
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


class TestAtPostPuppetAnnounce:
    def test_no_walk_announcement_on_puppet(self, monkeypatch, global_test_env):
        """INTENT: a puppet already standing in a room must not broadcast walk
        in/away announcements to the room's occupants when it assumes control."""
        monkeypatch.setattr(settings, "MAP_ENABLED", False)
        from atheriz.objects.session import Session

        node = Node(coord=Coord("test", 0, 0, 0), desc="A room.", symbol="#")
        puppet = Object.create(None, "Player", is_pc=True)
        observer = Object.create(None, "Observer")
        observer.msg = MagicMock()
        puppet.move_to(node)
        observer.move_to(node)
        observer.msg.reset_mock()

        session = Session()
        session.connection = MagicMock()
        puppet.session = session

        puppet.at_post_puppet()

        def get_text(c):
            if c.args:
                return str(c.args[0])
            return str(c.kwargs.get("text", ""))

        texts = [get_text(c) for c in observer.msg.call_args_list if get_text(c)]
        assert not any("walk" in t.lower() for t in texts), texts
