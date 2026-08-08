"""Issue tests: nodes must live in the global object cache.

Node.id is drawn from the shared unique-id counter and last_touched etc.
resolve object references through get(id). Nodes were never registered in
_ALL_OBJECTS, so node ids silently vanished from get() lookups. Nodes must
be registered on creation, evicted on removal/overwrite, re-registered on
handler load, excluded from object saves, and keep the id counter monotonic.
"""
from __future__ import annotations

import sqlite3
import os

from atheriz import database_setup, settings
from atheriz.globals.node import NodeHandler
from atheriz.globals.objects import _ALL_OBJECTS, get, save_objects
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeGrid
from atheriz.utils import Coord


class TestNodeCacheMembership:
    def test_node_registered_in_object_cache_on_create(self, global_test_env):
        """INTENT: creating a Node must immediately register it in the object
        cache, so get(node.id) resolves to it (last_touched, examine...)."""
        node = Node(coord=Coord("test", 1, 1, 0))
        assert get(node.id) == [node]

    def test_node_evicted_from_cache_on_handler_remove(self, global_test_env):
        """INTENT: NodeHandler.remove_node must evict the node's cache entry."""
        nh = NodeHandler()
        node = Node(coord=Coord("test", 2, 2, 0))
        nh.add_node(node)
        assert get(node.id) == [node]

        nh.remove_node(node.coord)
        assert get(node.id) == []

    def test_old_node_evicted_from_cache_on_grid_overwrite(self, global_test_env):
        """INTENT: overwriting a node at the same coords must evict the old
        node's cache entry so get(old_id) doesn't return a stale node."""
        grid = NodeGrid(area="test", z=0)
        node_a = Node(coord=Coord("test", 0, 0, 0))
        grid.add_node(node_a)
        assert get(node_a.id) == [node_a]

        node_b = Node(coord=Coord("test", 0, 0, 0))
        grid.add_node(node_b)
        assert get(node_a.id) == []
        assert get(node_b.id) == [node_b]

    def test_handler_clear_evicts_all_nodes(self, global_test_env):
        """INTENT: NodeHandler.clear must evict every cached node."""
        nh = NodeHandler()
        node = Node(coord=Coord("test", 3, 3, 0))
        nh.add_node(node)
        nh.clear()
        assert get(node.id) == []


class TestNodePersistence:
    def test_save_objects_skips_nodes(self, global_test_env):
        """INTENT: save_objects must not write nodes into the objects table;
        nodes are persisted by NodeHandler.save instead."""
        node = Node(coord=Coord("test", 4, 4, 0))
        obj = Object.create(None, "saveable")
        save_objects(force=True)

        db_path = os.path.join(settings.SAVE_PATH, "database.sqlite3")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM objects WHERE id=?", (node.id,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM objects WHERE id=?", (obj.id,))
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_node_reregistered_in_cache_after_handler_load(
        self, global_test_env
    ):
        """INTENT: a node restored from the database must re-enter the object
        cache; NodeHandler.load is the only registration point for pickled
        nodes. The id counter must also be bumped past loaded node ids so new
        nodes never collide."""
        nh = NodeHandler()
        node = Node(coord=Coord("TestAreaNC", 1, 1, 0))
        nh.add_node(node)
        nh.save()

        if database_setup._DATABASE:
            database_setup._DATABASE.close()
        database_setup._DATABASE = None
        database_setup._CLOSED = False
        _ALL_OBJECTS.clear()

        nh2 = NodeHandler()
        loaded = nh2.get_node(Coord("TestAreaNC", 1, 1, 0))
        assert loaded is not None
        assert get(node.id) == [loaded]

        new_node = Node(coord=Coord("TestAreaNC", 2, 2, 0))
        assert new_node.id > node.id