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
        self.move_to(node, link.name)

class WanderCommand(Command):
    key = "wander"
    desc = "Spawn 10 NPCs to your location to wander around"
    use_parser = True
    category = "Building"

    def setup_parser(self):
        self.parser.add_argument("count", nargs="?", type=int, default=10, help="Number of wanderers to spawn")
    
    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        count = args.count if args.count else 10
        
        start = time.time()
        for i in range(count):
            # Create a unique name for each wanderer to avoid collisions if called multiple times
            name = f"Wanderer {random.randint(1000, 9999)}"
            npc = Wanderer.create(caller=caller, name=name, is_npc=True, is_mapable=True, is_tickable=True)
            if npc:
                npc.move_to(caller.location)
        end = time.time()
        caller.msg(f"Spawned {count} NPCs in {(end - start) * 1000:.2f} milliseconds")