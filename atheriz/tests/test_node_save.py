import pytest
from atheriz.singletons.node import NodeHandler
from atheriz.objects.nodes import NodeArea, Transition, Door
from atheriz import settings
from pathlib import Path
import shutil
import dill
import os

TEST_SAVE_DIR = Path("test_node_save_data")

@pytest.fixture
def clean_save_dir():
    original_save_path = settings.SAVE_PATH
    settings.SAVE_PATH = str(TEST_SAVE_DIR)
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)
    TEST_SAVE_DIR.mkdir(parents=True, exist_ok=True)
    
    yield TEST_SAVE_DIR
    
    settings.SAVE_PATH = original_save_path
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)

def test_nodehandler_atomic_save(clean_save_dir):
    handler = NodeHandler()
    
    # Add some data
    area = NodeArea(name="TestArea")
    handler.add_area(area)
    
    trans = Transition(from_coord=("A1", 0, 0, 0), to_coord=("A2", 0, 0, 0), from_link="n")
    handler.add_transition(trans)
    
    door = Door(from_coord=("A1", 0, 0, 0), to_coord=("A2", 0, 0, 0), from_exit="n", to_exit="s")
    handler.add_door(door)
    
    # Save
    handler.save()
    
    # Verify files exist
    assert (TEST_SAVE_DIR / "areas").exists()
    assert (TEST_SAVE_DIR / "transitions").exists()
    assert (TEST_SAVE_DIR / "doors").exists()
    
    # Verify no .tmp files remain
    assert not list(TEST_SAVE_DIR.glob("*.tmp"))
    
    # Load and verify data
    with (TEST_SAVE_DIR / "areas").open("rb") as f:
        loaded_areas = dill.load(f)
        assert "TestArea" in loaded_areas
        
    with (TEST_SAVE_DIR / "transitions").open("rb") as f:
        loaded_transitions = dill.load(f)
        assert ("A2", 0, 0, 0) in loaded_transitions
        
    with (TEST_SAVE_DIR / "doors").open("rb") as f:
        loaded_doors = dill.load(f)
        assert ("A1", 0, 0, 0) in loaded_doors

def test_nodehandler_save_creates_dir(clean_save_dir):
    # Test that save() creates the directory if it doesn't exist
    shutil.rmtree(clean_save_dir)
    assert not clean_save_dir.exists()
    
    handler = NodeHandler()
    handler.save()
    
    assert clean_save_dir.exists()
