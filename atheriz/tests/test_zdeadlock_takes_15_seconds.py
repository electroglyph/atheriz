
import threading
import time
import sys
import os
import random
import pytest

# Ensure we can import the local package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import atheriz.settings as settings

# Force slow locks before importing objects to ensure they use safe access
settings.SLOW_LOCKS = True
settings.THREADSAFE_GETTERS_SETTERS = True

from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeLink
from atheriz.singletons.objects import add_object, get
from atheriz.singletons.get import get_unique_id, get_node_handler
from atheriz.commands.base_cmdset import CmdSet

# Ensure we have a clean slate for singletons if possible
# (In a single run script, this is fresh)

def test_stress_deadlock():
    print("--- Starting Deadlock Stress Test (Using Real Objects) ---")
    
    # 1. Setup Nodes
    # We need coords (area, x, y, z)
    # Area "TestArea", Z=0
    
    # Node 1
    room1 = Node(coord=("TestArea", 1, 0, 0), desc="This is Room 1")
    room1.id = get_unique_id()
    add_object(room1)
    
    # Node 2
    room2 = Node(coord=("TestArea", 2, 0, 0), desc="This is Room 2")
    room2.id = get_unique_id()
    add_object(room2)
    
    # Link them
    # Node.add_link expects a NodeLink
    link1_2 = NodeLink(name="East", coord=room2.coord)
    room1.add_link(link1_2)
    
    link2_1 = NodeLink(name="West", coord=room1.coord)
    room2.add_link(link2_1)
    
    # Also add to NodeHandler because move_to might check strict logic or simple location set
    nh = get_node_handler()
    nh.add_node(room1)
    nh.add_node(room2)

    npcs = []
    threads = []
    
    running = True
    deadlock_detected = False
    
    # 5 Movers
    for i in range(5):
        npc = Object()
        npc.id = get_unique_id()
        npc.name = f"Mover-{i}"
        npc.is_npc = True
        npc.internal_cmdset = CmdSet()
        add_object(npc)
        
        # Initial placement
        npc.location = room1
        room1.add_object(npc)
        
        npcs.append(npc)
        
    # 1 Looker
    looker = Object()
    looker.id = get_unique_id()
    looker.name = "Looker"
    looker.is_npc = True # or PC
    looker.internal_cmdset = CmdSet()
    add_object(looker)
    
    looker.location = room1
    room1.add_object(looker)
    
    npcs.append(looker)
    
    # Shared state for progress monitoring
    last_action_time = {}
    
    def mover_logic(npc):
        last_action_time[npc.name] = time.time()
        while running:
            try:
                current_loc = npc.location
                target_link = current_loc.links[0]
                target_node = nh.get_node(target_link.coord)
                
                npc.move_to(target_node, target_link.name)
                    
                last_action_time[npc.name] = time.time()
                time.sleep(random.uniform(0.1, 0.5))
            except Exception as e:
                print(f"Mover {npc.name} error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.5)

    def looker_logic(npc):
        last_action_time[npc.name] = time.time()
        while running:
            try:
                loc = npc.location
                _ = npc.at_look(loc)
                    
                last_action_time[npc.name] = time.time()
                time.sleep(random.uniform(0.1, 0.5))
            except Exception as e:
                print(f"Looker {npc.name} error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.5)

    # Start Mover Threads
    for i in range(5):
        t = threading.Thread(target=mover_logic, args=(npcs[i],), daemon=True)
        t.start()
        threads.append(t)
        
    # Start Looker Thread
    t_look = threading.Thread(target=looker_logic, args=(looker,), daemon=True)
    t_look.start()
    threads.append(t_look)
    
    # Deadlock Detector (Main Thread)
    start_time = time.time()
    formatted_start = time.strftime("%H:%M:%S", time.localtime(start_time))
    print(f"Test started at {formatted_start}. Running for 15 seconds...")
    
    try:
        while time.time() - start_time < 15:
            now = time.time()
            stalled = []
            for item in npcs:
                last = last_action_time.get(item.name, 0)
                if now - last > 1.0:
                    stalled.append(item.name)
            
            if stalled:
                print(f"POTENTIAL DEADLOCK DETECTED! Stalled threads: {stalled}")
                deadlock_detected = True
                running = False
                break
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping test...")
        
    running = False
    print("Stopping threads...")
    for t in threads:
        t.join(timeout=1.0)
        
    # Check for deadlocks
    assert not deadlock_detected, "Deadlock detected during stress test."
    print("SUCCESS: No deadlocks detected using real objects.")
