import dill
import pickle
from threading import RLock
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from atheriz.objects.base_obj import Object

def test_minimal():
    print("Testing minimal Object serialization...")
    char = Object() # This patches Object class
    char.name = "Test"
    
    for module in [pickle, dill]:
        print(f"\n--- Testing with {module.__name__} ---")
        print("Dumping...")
        data = module.dumps(char)
        
        print("Loading...")
        try:
            loaded = module.loads(data)
            print(f"Loaded successfully! Name: {loaded.name}")
        except Exception as e:
            print(f"Caught error: {type(e).__name__}: {e}")
            # import traceback
            # traceback.print_exc()

if __name__ == "__main__":
    test_minimal()
