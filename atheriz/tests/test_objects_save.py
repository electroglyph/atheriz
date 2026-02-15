import pytest
from atheriz.singletons.objects import save_objects, add_object, _ALL_OBJECTS, _OBJECT_MAP
from atheriz import settings
from pathlib import Path
import shutil
import dill

TEST_SAVE_DIR = Path("test_objects_save_data")

@pytest.fixture
def clean_save_dir():
    original_save_path = settings.SAVE_PATH
    settings.SAVE_PATH = str(TEST_SAVE_DIR)
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)
    TEST_SAVE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Mocking Object for testing
    class MockObject:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    original_all_objects = _ALL_OBJECTS.copy()
    original_object_map = _OBJECT_MAP.copy()
    _ALL_OBJECTS.clear()
    _OBJECT_MAP.clear()
    
    yield TEST_SAVE_DIR, MockObject
    
    settings.SAVE_PATH = original_save_path
    _ALL_OBJECTS.clear()
    _ALL_OBJECTS.update(original_all_objects)
    _OBJECT_MAP.clear()
    _OBJECT_MAP.update(original_object_map)
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)

def test_save_objects_atomic(clean_save_dir):
    save_dir, MockObject = clean_save_dir
    
    obj1 = MockObject(1, "TestObj1")
    add_object(obj1)
    
    save_objects()
    
    assert (save_dir / "objects").exists()
    assert (save_dir / "object_map").exists()
    assert not list(save_dir.glob("*.tmp"))
    
    with (save_dir / "objects").open("rb") as f:
        loaded_objects = dill.load(f)
        assert 1 in loaded_objects
        assert loaded_objects[1].name == "TestObj1"

def test_save_objects_creates_dir(clean_save_dir):
    save_dir, MockObject = clean_save_dir
    shutil.rmtree(save_dir)
    assert not save_dir.exists()
    
    save_objects()
    assert save_dir.exists()
