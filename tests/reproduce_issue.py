
import os
import sys
import threading
import time
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atheriz.singletons.get import get_node_handler
from atheriz.singletons.objects import _ALL_OBJECTS
from atheriz.objects.nodes import Node, NodeLink
from atheriz.objects.base_obj import Object

def move_loop(npc, node1, node2, iterations, results):
    name = npc.name
    try:
        for i in range(iterations):
            # Move to target node
            prev_node = npc.location
            target_node = node2 if prev_node == node1 else node1
            exit_name = "east" if target_node == node2 else "west"
            other_exit = "west" if target_node == node2 else "east"

            success = npc.move_to(target_node, exit_name)
            if not success:
                results.append(f"[{name}] Iteration {i}: Move to {target_node.coord} FAILED")
                return

            # Post-move checks
            if npc.id not in target_node._contents:
                results.append(f"[{name}] Iteration {i}: NOT in target node _contents after move")
            
            if prev_node and npc.id in prev_node._contents:
                results.append(f"[{name}] Iteration {i}: STILL in previous node _contents after move")

            if target_node != npc.location:
                results.append(f"[{name}] Iteration {i}: npc.location {npc.location} != target {target_node}")

            # Check internal_cmdset for exits
            found_exit = False
            for cmd in npc.internal_cmdset.get_all():
                if cmd.key == other_exit and cmd.tag == "exits":
                    found_exit = True
                    break
            
            if not found_exit:
                results.append(f"[{name}] Iteration {i}: Exit '{other_exit}' NOT found in internal_cmdset at {target_node.coord}")

    except Exception as e:
        results.append(f"[{name}] CRASHED: {e}")

def test_repro():
    nh = get_node_handler()
    nh.clear()
    _ALL_OBJECTS.clear()
    
    print("--- REPRO START ---")
    
    # 1. Setup Nodes
    node1 = Node(("test", 0, 0, 0), "Node 1")
    node2 = Node(("test", 1, 0, 0), "Node 2")
    
    node1.links = [NodeLink("east", ("test", 1, 0, 0))]
    node2.links = [NodeLink("west", ("test", 0, 0, 0))]
    
    nh.add_node(node1)
    nh.add_node(node2)
    
    # 2. Create 5 NPCs in Node 1
    npcs = []
    for i in range(5):
        npc = Object.create(None, f"NPC_{i}", is_npc=True)
        npc.move_to(node1, force=True)
        npcs.append(npc)
        print(f"Created NPC: {npc.name}, ID: {npc.id}")

    # 3. Start Threads
    iterations = 10000
    results = []
    threads = []
    
    print(f"Starting {len(npcs)} threads moving {iterations} times each...")
    for npc in npcs:
        t = threading.Thread(target=move_loop, args=(npc, node1, node2, iterations, results))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # 4. Final Report
    if not results:
        print("SUCCESS: All moves completed without inconsistency.")
    else:
        print(f"FAILURE: {len(results)} inconsistencies detected!")
        # Only show first 10 to avoid spam
        for r in results[:10]:
            print(f"  - {r}")
        if len(results) > 10:
            print(f"  ... and {len(results) - 10} more.")
        
        # Exit with non-zero code if there are failures
        sys.exit(1)

if __name__ == "__main__":
    test_repro()
