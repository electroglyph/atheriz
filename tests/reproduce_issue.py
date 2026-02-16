
import dill
import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atheriz import settings
settings.SAVE_PATH = "test_repro_data"
# Create save dir if not exists
Path(settings.SAVE_PATH).mkdir(exist_ok=True)

from atheriz.objects.nodes import Node, NodeGrid, NodeArea
from atheriz.objects.base_obj import Object
from atheriz.singletons.objects import _ALL_OBJECTS, add_object, save_objects, load_objects
from atheriz.singletons.get import get_node_handler

def log(msg):
    print(msg)
    with open("repro_output.txt", "a") as f:
        f.write(msg + "\n")

def test_reproduction():
    with open("repro_output.txt", "w") as f:
        f.write("Starting improved reproduction test...\n")
    
    # Setup
    nh = get_node_handler()
    nh.clear()
    _ALL_OBJECTS.clear()
    
    # 1. Create Nodes
    nodeA = Node(coord=("TestArea", 0, 0, 0), desc="Room A")
    nodeB = Node(coord=("TestArea", 1, 0, 0), desc="Room B")
    
    # Add to NodeHandler
    nh.add_node(nodeA)
    nh.add_node(nodeB)
    
    # 2. Create Character
    char = Object.create(None, "PlayerChar", is_pc=True)
    char.location = nodeA
    nodeA._contents.add(char.id)
    
    log(f"Setup: Char {char.id} in Node A {nodeA.coord}")
    log(f"Node A contents: {nodeA._contents}")
    
    # 3. Perform Move using move_to
    log("Moving Char to Node B...")
    success = char.move_to(nodeB)
    
    log(f"Move successful: {success}")
    log(f"Char location: {char.location.coord if char.location else 'None'}")
    log(f"Node A contents: {nodeA._contents}")
    log(f"Node B contents: {nodeB._contents}")
    
    if char.id not in nodeB._contents:
        log("FAILURE: Char ID missing from Node B contents after move_to!")
    else:
        log("SUCCESS: Char ID found in Node B contents.")

    # 4. Check contents property
    log(f"Node B contents property: {[o.id for o in nodeB.contents]}")
    if char.id not in [o.id for o in nodeB.contents]:
        log("FAILURE: Char ID missing from Node B.contents property!")

    # 5. Persist and Reload
    log("Saving objects and nodes...")
    save_objects()
    nh.save()
    
    log("Resetting singletons and reloading...")
    nh.clear()
    _ALL_OBJECTS.clear()
    
    # Reload NodeHandler (this will reload areas from 'save/areas')
    # Use the same nh instance as it re-initializes from disk on save() or via constructor?
    # Actually nh.__init__ loads from disk.
    new_nh = type(nh)() 
    load_objects()
    
    reloaded_nodeB = new_nh.get_node(("TestArea", 1, 0, 0))
    if not reloaded_nodeB:
        log("FAILURE: Could not reload Node B!")
    else:
        log(f"Reloaded Node B contents: {reloaded_nodeB._contents}")
        log(f"Type of _contents: {type(reloaded_nodeB._contents)}")
        if char.id not in reloaded_nodeB._contents:
            log("FAILURE: Char ID missing after reload!")
        else:
            log("SUCCESS: Char ID preserved after reload.")

if __name__ == "__main__":
    try:
        test_reproduction()
    except Exception as e:
        import traceback
        log(f"EXCEPTION: {e}")
        log(traceback.format_exc())
