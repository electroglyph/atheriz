import math
from atheriz.coord import Coord
from atheriz.utils import get_dir, dist_3d

def test_get_dir():
    origin = Coord("limbo", 0, 0, 0)
    
    # Simple cardinals
    assert get_dir(origin, Coord("limbo", 0, 1, 0)) == "north"
    assert get_dir(origin, Coord("limbo", 0, -1, 0)) == "south"
    assert get_dir(origin, Coord("limbo", 1, 0, 0)) == "east"
    assert get_dir(origin, Coord("limbo", -1, 0, 0)) == "west"
    
    # Diagonals
    assert get_dir(origin, Coord("limbo", 1, 1, 0)) == "northeast"
    assert get_dir(origin, Coord("limbo", -1, 1, 0)) == "northwest"
    assert get_dir(origin, Coord("limbo", 1, -1, 0)) == "southeast"
    assert get_dir(origin, Coord("limbo", -1, -1, 0)) == "southwest"
    
    # Far away
    assert get_dir(origin, Coord("limbo", 10, 5, 0)) == "northeast"
    assert get_dir(origin, Coord("limbo", -10, -5, 0)) == "southwest"
    
    # Same spot
    assert get_dir(origin, origin) == ""
    
    # Vertical (should not affect get_dir currently as it's 2D)
    assert get_dir(origin, Coord("limbo", 0, 1, 10)) == "north"
    assert get_dir(origin, Coord("limbo", 0, 0, 10)) == ""
    
    # Many Z levels above, slightly North
    assert get_dir(origin, Coord("limbo", 0, 1, 100)) == "north"
    
    # Many Z levels below, slightly South
    assert get_dir(origin, Coord("limbo", 0, -1, -100)) == "south"

def test_dist_3d():
    origin = Coord("limbo", 0, 0, 0)
    
    # Simple axes
    assert dist_3d(origin, Coord("limbo", 3, 0, 0)) == 3.0
    assert dist_3d(origin, Coord("limbo", 0, 4, 0)) == 4.0
    assert dist_3d(origin, Coord("limbo", 0, 0, 5)) == 5.0
    
    # Diagonal 2D
    assert dist_3d(origin, Coord("limbo", 3, 4, 0)) == 5.0
    
    # Diagonal 3D
    # sqrt(1^2 + 1^2 + 1^2) = sqrt(3)
    assert math.isclose(dist_3d(origin, Coord("limbo", 1, 1, 1)), math.sqrt(3))
    
    # Mixed Coords and tuples (to verify backward compatibility)
    assert dist_3d(origin, ("limbo", 0, 3, 4, 0)) == 5.0
    assert dist_3d(("limbo", 0, 0, 0, 0), ("limbo", 0, 3, 4, 0)) == 5.0
    
    # 3-tuples (x, y, z)
    assert dist_3d((0, 0, 0), (3, 4, 0)) == 5.0


def test_get_dir_mixed_coord_and_tuple_consistency():
    origin = Coord("test", 0, 0, 0)
    dest_coord = Coord("test", 1, 0, 0)
    dest_tuple_3 = (1, 0, 0)
    dest_tuple_4 = ("test", 1, 0, 0)
    assert get_dir(origin, dest_coord) == "east"
    assert get_dir(origin, dest_tuple_4) == "east", "4-tuple should match Coord"
    assert get_dir(origin, dest_tuple_3) == "east", "3-tuple (x,y,z) east should be east, not mis-indexed"

def test_get_dir_north_with_mixed_types():
    origin = Coord("test", 0, 0, 0)
    dest_coord_north = Coord("test", 0, 1, 0)
    dest_tuple_3_north = (0, 1, 0)
    assert get_dir(origin, dest_coord_north) == "north"
    assert get_dir(origin, dest_tuple_3_north) == "north", "3-tuple north should be north, index mix gives wrong direction"

def test_get_dir_area_mismatch_with_mixed_lengths():
    assert get_dir(Coord("a", 0, 0, 0), Coord("b", 0, 1, 0)) == ""
    assert get_dir(Coord("a", 0, 0, 0), ("a", 0, 1, 0)) == "north"
    assert get_dir((0, 0, 0), Coord("test", 0, 1, 0)) == "north"

def test_get_dir_index_consistency_across_types():
    o = Coord("limbo", 5, 5, 0)
    d = Coord("limbo", 6, 6, 0)
    assert get_dir(o, d) == "northeast"
    assert get_dir((5, 5, 0), (6, 6, 0)) == "northeast"
