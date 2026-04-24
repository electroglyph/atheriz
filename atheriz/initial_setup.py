from atheriz.objects.base_channel import Channel
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.globals.get import get_node_handler, get_map_handler, get_game_time
from atheriz.globals.map import MapInfo
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.globals.objects import add_object, save_objects
import atheriz.settings as settings
from atheriz.database_setup import do_setup as do_db_setup
from atheriz.logger import logger
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.network.connection import BaseConnection as Connection
    from atheriz.objects.base_obj import Object


class PushCommand(Command):
    key = "push"
    desc = "It's a button, you can push it."
    category = "Danger?"
    use_parser = False

    def run(self, caller: Object, args):
        loc: Node | None = caller.location
        if loc:
            loc.msg_contents(text="BEEEEEP!")


class AlarmObject(Object):
    def at_alarm(self, time, data):
        self.emit_sound(
            "A robotic voice intones: ",
            "Hands to ACTION STATIONS! Hands to ACTION STATIONS! Assume damage control state one condition ZULU. This is not a drill!",
            120.0,
            True,
        )


LIMBO_AREA = "limbo"
LIMBO_GRID = 9
LIMBO_CENTER = LIMBO_GRID // 2  # 4
LIMBO_DESC = "You are in a vast nothingness."


def do_setup(username=None, password=None):
    logger.info("Setting up initial world state...")
    do_db_setup()
    nh = get_node_handler()

    # Build a 9x9x9 cube for the limbo area; the center node (4,4,4) is the default home.
    area = NodeArea(name=LIMBO_AREA)
    for z in range(LIMBO_GRID):
        grid = NodeGrid(area=LIMBO_AREA, z=z)
        for x in range(LIMBO_GRID):
            for y in range(LIMBO_GRID):
                node = Node(coord=(LIMBO_AREA, x, y, z), desc=LIMBO_DESC)
                grid.nodes[(x, y)] = node
        area.add_grid(grid)
    DIRS = [
        ("North", "n", 0, 1, 0, "South", "s"),
        ("East", "e", 1, 0, 0, "West", "w"),
        ("Up", "u", 0, 0, 1, "Down", "d"),
    ]
    for z in range(LIMBO_GRID):
        grid = area.get_grid(z)
        for x in range(LIMBO_GRID):
            for y in range(LIMBO_GRID):
                node = grid.nodes[(x, y)]
                for name, alias, dx, dy, dz, rev_name, rev_alias in DIRS:
                    nx, ny, nz = x + dx, y + dy, z + dz
                    if 0 <= nx < LIMBO_GRID and 0 <= ny < LIMBO_GRID and 0 <= nz < LIMBO_GRID:
                        ng = grid if dz == 0 else area.get_grid(nz)
                        if ng:
                            neighbor = ng.nodes.get((nx, ny))
                            if neighbor:
                                node.add_link(NodeLink(name=name, coord=(LIMBO_AREA, nx, ny, nz), aliases=[alias]))
                                neighbor.add_link(
                                    NodeLink(name=rev_name, coord=(LIMBO_AREA, x, y, z), aliases=[rev_alias])
                                )

    nh.add_area(area)

    mh = get_map_handler()
    for z in range(LIMBO_GRID):
        mi = MapInfo(name=LIMBO_AREA)
        for x in range(LIMBO_GRID):
            for y in range(LIMBO_GRID):
                mi.pre_grid[(x, y)] = settings.ROOM_PLACEHOLDER
                mi.place_walls((x, y), settings.SINGLE_WALL_PLACEHOLDER)
        mi.pre_render()
        mh.set_mapinfo(LIMBO_AREA, z, mi)
    mh.save()
    nh.save()

    if not username:
        import os

        username = os.environ.get("ATHERIZ_SUPERUSER_USERNAME")
        if not username:
            username = input("Enter superuser username: ").strip()

    if not password:
        import os
        import getpass

        password = os.environ.get("ATHERIZ_SUPERUSER_PASSWORD")
        if not password:
            password = getpass.getpass("Enter superuser password: ")

    alarm_node = nh.get_node((LIMBO_AREA, 0, 0, LIMBO_GRID - 1))
    alarm_obj = AlarmObject.create(
        None,
        "A flashing dashboard",
        "A large display showing a multitude of plots and status readouts.",
        is_item=True,
        aliases=["dashboard"],
    )
    alarm_obj.move_to(alarm_node)

    gt = get_game_time()
    gt.add_alarm("?", "0", alarm_obj, repeat=True)
    gt.save()

    account = Account.create(username, password)
    print(f"Creating character '{username}'...")
    character = Object.create(None, username, "", is_pc=True)
    nh = get_node_handler()
    home = nh.get_node(settings.DEFAULT_HOME)
    character.home = home
    character.privilege_level = settings.Privilege.Admin
    character.move_to(home)
    button = Object.create(
        None,
        "A big red button",
        "A large button that glows with an ominous red light. Wonder if it does anything...",
        is_item=True,
        aliases=["button"],
    )
    # only allow builders to pick it up
    button.add_lock("get", lambda x: x.is_builder)
    button.external_cmdset.add(PushCommand())
    button.move_to(home)
    account.add_character(character)
    c = Channel.create("Server")
    c.add_lock("send", lambda x: x.is_builder)
    c.add_lock("view", lambda x: x.is_builder)
    c.desc = "for server announcements"
    character.subscribe(c)
    save_objects()
    nh.save()
    logger.info("Initial world state set up.")
