import pytest
from atheriz.utils import Coord
import tempfile
import shutil
from unittest.mock import MagicMock

from atheriz.commands.loggedin.maze import gen_map_and_grid
from atheriz.objects.nodes import NodeArea, NodeLink
from atheriz.globals.get import get_node_handler
from atheriz.pathfind import astar
from atheriz.globals.objects import _ALL_OBJECTS
from atheriz import database_setup, settings
from atheriz.globals import get

@pytest.fixture(autouse=True)
def temp_env():
    old_save_path = settings.SAVE_PATH
    temp_dir = tempfile.mkdtemp()
    settings.SAVE_PATH = temp_dir
    
    database_setup.do_setup()
    get._NODE_HANDLER = None
    _ALL_OBJECTS.clear()
    
    yield
    
    import atheriz.database_setup as db_mod
    if db_mod._DATABASE is not None:
        db_mod._DATABASE.close()
    db_mod._DATABASE = None

    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass
    settings.SAVE_PATH = old_save_path
    get._NODE_HANDLER = None
    _ALL_OBJECTS.clear()

def test_maze_astar():
    nh = get_node_handler()
    
    width = 50
    height = 20
    map1, grid1 = gen_map_and_grid(width, height, "maze1")
    map2, grid2 = gen_map_and_grid(width, height, "maze2")
    map3, grid3 = gen_map_and_grid(width, height, "maze3")
    
    area1 = NodeArea("maze1")
    area2 = NodeArea("maze2")
    area3 = NodeArea("maze3")
    
    area1.add_grid(grid1)
    area2.add_grid(grid2)
    area3.add_grid(grid3)
    
    nh.add_area(area1)
    nh.add_area(area2)
    nh.add_area(area3)
    
    maze1_exit = list(grid1.nodes.values())[-1]
    maze2_exit = list(grid2.nodes.values())[-1]
    maze3_exit = list(grid3.nodes.values())[-1]
    
    maze1_exit.add_link(NodeLink("down", Coord("maze2", 0, 0, 0), ["d"]))
    maze2_exit.add_link(NodeLink("down", Coord("maze3", 0, 0, 0), ["d"]))
    maze3_exit.add_link(NodeLink("down", Coord("maze1", 0, 0, 0), ["d"]))
    
    # Test pathfinding from maze1 start to maze3 exit
    start_node = nh.get_node(Coord("maze1", 0, 0, 0))
    if not start_node:
        start_node = list(grid1.nodes.values())[0]
        
    end_node = maze3_exit
    
    caller = MagicMock()
    
    success, path, deadend = astar(start_node, end_node, caller)
    
    msg_calls = [call[0][0] for call in caller.msg.call_args_list]
    print(f"\nStart Node: {start_node.coord}")
    print(f"End Node: {end_node.coord}")
    print(f"Path Length: {len(path)}")
    print(f"Explored Nodes (closed_list length): {len(deadend)}")
    print(f"Start Grid Length: {len(start_node.grid)}")
    print(f"Total reachable nodes in 3 grids approx: {len(grid1) + len(grid2) + len(grid3)}")
    print(f"Max expected iterations from pathfind.py: {len(start_node.grid) * 3}")
    print(f"Caller messages: {msg_calls}")
    
    # Ideally should be True, but will likely fail due to max iterations hit
    assert success is True, f"Pathfinding failed, explored {len(deadend)} nodes"
