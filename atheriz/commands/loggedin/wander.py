from atheriz.commands.base_cmd import Command
from atheriz.objects.base_obj import Object
from atheriz.singletons.get import get_node_handler
import time
from typing import TYPE_CHECKING
import random
if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.websocket import Connection
    from atheriz.objects.nodes import Node


class Wanderer(Object):
    def at_tick(self):
        loc: Node | None = self.location
        if not loc:
            return
        if not loc.links:
            return
        nh = get_node_handler()
        link = random.choice(loc.links)
        node = nh.get_node(link.coord)
        if not node:
            return
        self.move_to(node)

class WanderCommand(Command):
    key = "wander"
    desc = "Spawn 10 NPCs to your location to wander around"
    use_parser = False
    category = "Building"
    
    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        count = 10
        start = time.time()
        for i in range(count):
            npc = Wanderer.create(caller.session, f"Wanderer {i}", f"Wanderer {i}", is_npc=True, is_mapable=True, is_tickable=True)
            npc.move_to(caller.location)
        end = time.time()
        caller.msg(f"Spawned {count} NPCs in {(end - start) * 1000:.2f} milliseconds")