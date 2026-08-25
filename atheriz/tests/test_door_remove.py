import pytest
from unittest.mock import MagicMock, patch, call
from atheriz.utils import Coord
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.node import NodeHandler
from atheriz.objects.base_door import Door
from atheriz.objects.base_obj import Object
from atheriz.pathfind import astar
from atheriz.commands.loggedin.exit import ExitCommand
from atheriz import settings


class MockMapInfo:
    def __init__(self):
        self.lock = MagicMock()
        self.lock.__enter__ = MagicMock(return_value=None)
        self.lock.__exit__ = MagicMock(return_value=False)
        self.post_grid = {}
        self.pre_grid = None
        self.map_changed = False
    def update_grid(self, coord, symbol):
        pass
    def render(self, force=False):
        pass

class MockMapHandler:
    def get_mapinfo(self, area, z):
        return MockMapInfo()

class TestRemoveDoorCleansLinkAndGlyph:

    def _setup_door_via_handler(self, area_name="RemoveDoorArea"):
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name=area_name)
        grid = NodeGrid(area=area_name, z=0)
        n1 = Node(coord=Coord(area_name, 0, 0, 0))
        n2 = Node(coord=Coord(area_name, 0, 2, 0))
        n1.add_link(NodeLink("north", Coord(area_name, 0, 2, 0), ["n"]))
        n2.add_link(NodeLink("south", Coord(area_name, 0, 0, 0), ["s"]))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)
        door = Door.create(
            from_coord=Coord(area_name, 0, 0, 0),
            from_exit="north",
            to_coord=Coord(area_name, 0, 2, 0),
            to_exit="south",
            symbol_coord=(0, 1),
            closed_symbol=settings.NS_CLOSED_DOOR,
            open_symbol=settings.NS_OPEN_DOOR1,
            closed=True,
            locked=False,
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)
        return nh, n1, n2, door, mh

    def test_remove_door_remove_door_deletes_links(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler()
        assert n1.get_link_by_name("north") is not None
        assert n2.get_link_by_name("south") is not None
        assert nh.get_doors(n1.coord) is not None
        assert "north" in nh.get_doors(n1.coord)
        assert "south" in nh.get_doors(n2.coord)

        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
        assert n1.has_link_name("north") is False
        assert n2.has_link_name("south") is False
        assert n1.get_link_by_name("n") is None

    def test_remove_door_remove_door_deletes_doors_dict(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea2")
        assert nh.get_doors(n1.coord) is not None
        assert nh.get_doors(n2.coord) is not None
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)
        doors1 = nh.get_doors(n1.coord)
        doors2 = nh.get_doors(n2.coord)
        if doors1:
            assert "north" not in doors1
        else:
            assert doors1 is None or "north" not in (doors1 or {})
        if doors2:
            assert "south" not in doors2

    def test_remove_door_remove_door_display_exits_no_longer_shows(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea3")
        disp_before = n1.get_display_exits()
        assert "north" in disp_before
        disp_before2 = n2.get_display_exits()
        assert "south" in disp_before2

        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        disp_after = n1.get_display_exits()
        assert "north" not in disp_after
        disp_after2 = n2.get_display_exits()
        assert "south" not in disp_after2

    def test_remove_door_remove_door_player_cannot_use_exit(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea4")
        player = Object.create(None, "Adventurer", is_pc=True)
        player.location = n1
        n1.add_object(player)
        assert n1.get_link_by_name("north") is not None
        found_before = any(getattr(c, "key", None) == "north" or getattr(c, "name", None) == "north" for c in player.internal_cmdset.commands) if hasattr(player.internal_cmdset, "commands") else False
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        assert n1.get_link_by_name("north") is None
        with patch("atheriz.pathfind.get_node_handler", return_value=nh), \
             patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
            success, path, _ = astar(n1, n2)
            assert success is False

        cmd = ExitCommand()
        cmd.caller_id = player.id
        cmd.location = n1.coord
        cmd.destination = n2.coord
        cmd.name = "north"
        cmd.key = "north"
        assert nh.get_node(n1.coord) == n1
        assert n1.get_link_by_name("north") is None

    def test_remove_door_remove_door_both_coords_cleaned(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea5")
        assert nh.get_doors(n1.coord)["north"] is door
        assert nh.get_doors(n2.coord)["south"] is door
        with patch("atheriz.globals.node.get_map_handler", return_value=mh):
            nh.remove_door(door)
        d1 = nh.get_doors(n1.coord)
        d2 = nh.get_doors(n2.coord)
        assert d1 is None or "north" not in d1
        assert d2 is None or "south" not in d2
        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None

    def test_remove_door_remove_door_via_door_create_and_add_door_then_remove(self, global_test_env):
        nh = NodeHandler()
        mh = MockMapHandler()
        area = NodeArea(name="RemoveDoorArea6")
        grid = NodeGrid(area="RemoveDoorArea6", z=0)
        n1 = Node(coord=Coord("RemoveDoorArea6", 0, 0, 0))
        n2 = Node(coord=Coord("RemoveDoorArea6", 0, 2, 0))
        n1.add_link(NodeLink("north", Coord("RemoveDoorArea6", 0, 2, 0)))
        n2.add_link(NodeLink("south", Coord("RemoveDoorArea6", 0, 0, 0)))
        grid.add_node(n1)
        grid.add_node(n2)
        area.add_grid(grid)
        nh.add_area(area)

        door = Door.create(
            from_coord=Coord("RemoveDoorArea6", 0, 0, 0),
            from_exit="north",
            to_coord=Coord("RemoveDoorArea6", 0, 2, 0),
            to_exit="south",
            symbol_coord=(0, 1),
            closed_symbol="X",
            open_symbol="O",
        )
        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.add_door(door)

        assert n1.get_link_by_name("north") is not None
        assert n2.get_link_by_name("south") is not None

        with patch("atheriz.globals.node.get_map_handler", return_value=mh), \
             patch("atheriz.objects.base_door.get_map_handler", return_value=mh):
            nh.remove_door(door)

        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
        assert n1.get_display_exits() == "" or "north" not in n1.get_display_exits()
        assert n2.get_display_exits() == "" or "south" not in n2.get_display_exits()

    def test_remove_door_remove_door_twice_idempotent(self, global_test_env):
        nh, n1, n2, door, mh = self._setup_door_via_handler("RemoveDoorArea7")
        with patch("atheriz.globals.node.get_map_handler", return_value=mh):
            nh.remove_door(door)
            nh.remove_door(door)
        assert n1.get_link_by_name("north") is None
        assert n2.get_link_by_name("south") is None
