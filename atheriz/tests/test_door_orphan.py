"""Issue tests: the `door` command removes the node a player is standing on
without relocating them, stranding the player in limbo.

When a door is built, any node occupying the door's coordinate is removed via
`nh.remove_node(...)` (`commands/loggedin/door.py`). Players whose `location`
points at that node are never moved, leaving their location a node that no
longer exists in the world grid.
"""
from __future__ import annotations

from atheriz.commands.loggedin.door import DoorCommand
from atheriz.globals.get import get_node_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.tests.fakes import MockCaller, make_args
from atheriz.utils import Coord


class TestDoorCreation:
    def test_door_creation_relocates_player_on_replaced_node(self, global_test_env):
        """INTENT: a player standing on the node that becomes a door must not
        be stranded; their location must still resolve to a live node."""
        nh = get_node_handler()
        origin = Node(Coord("test", 0, 0, 0))
        door_node = Node(Coord("test", 0, 1, 0))
        dest = Node(Coord("test", 0, 2, 0))
        for n in (origin, door_node, dest):
            nh.add_node(n)

        player = Object.create(None, "stranded", is_pc=True)
        player.location = door_node
        door_node.add_object(player)

        caller = MockCaller(name="builder", location=origin)

        cmd = DoorCommand()
        cmd.run(
            caller,
            make_args(
                north=True,
                south=False,
                east=False,
                west=False,
                up=False,
                down=False,
                remove=False,
            ),
        )

        assert nh.get_node(player.location.coord) is player.location
