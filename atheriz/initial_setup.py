from atheriz.objects.base_channel import Channel
from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink
from atheriz.singletons.map import MapInfo
from atheriz.singletons.get import get_node_handler, get_map_handler
from atheriz.objects.base_obj import Object
from atheriz.objects.base_account import Account
from atheriz.singletons.objects import add_object, save_objects
import atheriz.settings as settings
from atheriz.logger import logger
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.websocket import Connection
    from atheriz.objects.base_obj import Object


class PushCommand(Command):
    key = "push"
    desc = "It's a button, you can push it."
    category = "Danger?"
    use_parser = False

    def run(self, caller: Connection | Object, args):
        loc: Node = caller.location
        if loc:
            loc.msg_contents(text="BEEEEEP!")


def do_setup(username=None, password=None):
    logger.info("Setting up initial world state...")
    nh = get_node_handler()
    n = Node(
        settings.DEFAULT_HOME,
        desc=f"Welcome to {settings.SERVERNAME}, type `help` for a list of available commands.",
    )
    # coordinates can be defined before they exist, for instance, limbo area doesn't exist yet
    n2 = Node(("limbo", 0, 0, -1), desc="You are in a vast nothingness.")
    n.add_link(NodeLink("down", ("limbo", 0, 0, -1), ["d"]))
    n2.add_link(NodeLink("up", ("limbo", 0, 0, 0), ["u"]))
    nh.add_node(n)
    nh.add_node(n2)
    nh.save()
    mh = get_map_handler()
    mi1 = MapInfo("limbo")
    with mi1.lock:
        mi1.pre_grid[(0, 0)] = settings.ROOM_PLACEHOLDER
        mi1.place_walls((0, 0), settings.DOUBLE_WALL_PLACEHOLDER)
    mi2 = MapInfo("nothing")
    with mi2.lock:
        mi2.pre_grid[(0, 0)] = settings.ROOM_PLACEHOLDER
        mi2.place_walls((0, 0), settings.ROUNDED_WALL_PLACEHOLDER)
    mh.set_mapinfo("limbo", 0, mi1)
    mh.set_mapinfo("limbo", -1, mi2)

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

    account = Account.create(username, password)
    print(f"Creating character '{username}'...")
    character = Object.create(None, username, "", is_pc=True)
    nh = get_node_handler()
    home = nh.get_node(settings.DEFAULT_HOME)
    character.home = home
    character.privilege_level = 4
    character.move_to(home)
    button = Object.create(
        None,
        "A big red button",
        "A large button that glows with an ominous red light. Wonder if it does anything...",
        is_item=True,
        aliases=["button"],
    )
    button.add_lock("get", lambda x: x.is_builder)
    button.external_cmdset.add(PushCommand())
    button.move_to(home)
    account.add_character(character)
    c = Channel.create("Server")
    c.desc = "for server announcements"
    character.subscribe(c)
    save_objects()
    nh.save()
    mh.save()
    logger.info("Initial world state set up.")
