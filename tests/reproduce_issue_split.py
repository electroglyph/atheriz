
import dill
import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atheriz.objects.nodes import Node
from atheriz.objects.base_obj import Object

from atheriz.singletons.get import get_node_handler

def log(msg):
    print(msg)

def test_reproduction():
    nh = get_node_handler()
    
    log("Creating Node A and Character...")
    nodeA = Node(coord=("TestArea", 0, 0, 0))
    nh.add_node(nodeA) # Register with handler
    
    char = Object()
    char.id = 1
    char.name = "TestChar"
    
    # Put char in node
    char.location = nodeA
    nodeA._contents.add(char.id)
    
    log(f"Initial: char.location is nodeA: {char.location is nodeA}")
    
    # Simulate saving to separate files
    log("Simulating save to separate files...")
    char_data = dill.dumps(char)
    node_data = dill.dumps(nodeA)
    
    # Clear handler to simulate fresh load
    nh.clear()
    
    # Simulate loading from separate files
    log("Simulating load from separate files...")
    loaded_char = dill.loads(char_data)
    loaded_node = dill.loads(node_data)
    
    # After loading, the "real" node must be put back in the handler
    nh.add_node(loaded_node)
    
    log(f"Loaded: char.location is node object: {loaded_char.location}")
    log(f"Loaded: char.location is loaded_node: {loaded_char.location is loaded_node}")
    
    if loaded_char.location is not loaded_node:
        log("FAILURE: Cross-reference broken! Ghost room created.")
        log(f"ID of Ghost Node: {id(loaded_char.location)}")
        log(f"ID of Real Node: {id(loaded_node)}")
    else:
        log("SUCCESS: Cross-reference preserved thanks to NodeHandler property!")

    # SIMULATE OLD DATA MIGRATION
    log("\nSimulating migration from old data format...")
    old_char_state = {
        "id": 3,
        "name": "OldChar",
        "location": nodeA, # Old format: direct node reference
        "home": nodeA,     # Old format
    }
    
    # Create an object and manually set its state to simulate unpickling old data
    migrated_char = Object()
    migrated_char.__setstate__(old_char_state)
    
    log(f"Migrated: _location is coord: {migrated_char._location == nodeA.coord}")
    log(f"Migrated: _home is coord: {migrated_char._home == nodeA.coord}")
    log(f"Migrated: location property returns Node: {migrated_char.location is nodeA}")
    log(f"Migrated: home property returns Node: {migrated_char.home is nodeA}")
    
    if migrated_char.location is nodeA and migrated_char.home is nodeA:
        log("SUCCESS: Migration logic working correctly!")
    else:
        log("FAILURE: Migration logic failed!")

    # Moving in reality should now work because char.location looks up the REAL node
    log("\nSimulating movement in 'Real' node...")
    # Someone else moves into the real node
    char2_id = 2
    loaded_node._contents.add(char2_id)
    
    log(f"Real Node contents: {loaded_node._contents}")
    log(f"Ghost Node contents (char's view): {loaded_char.location._contents}")
    
    if char2_id not in loaded_char.location._contents:
        log("FAILURE: Char cannot see others moving into the real room!")
    else:
        log("SUCCESS: Char sees updates via NodeHandler lookup.")

if __name__ == "__main__":
    test_reproduction()
