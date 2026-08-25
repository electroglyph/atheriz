"""Issue tests: `load_objects()` must not iterate the live object registry
while running `resolve_relations()` hooks (objects.py:172-175).

A tuple (node-coordinate) `location` lazily constructs `NodeHandler` during
relation resolution, and `NodeHandler.load()` registers every node via
`add_object()` — mutating the registry mid-iteration -> RuntimeError on
startup (game folder).

INTENT: `load_objects()` resolves relations against a snapshot; objects
registered during the pass must not crash the load and must stay in the
registry.
"""
from __future__ import annotations

from atheriz.globals.objects import get, load_objects, save_objects
from atheriz.objects.base_obj import Object


class _FakeNode:
    is_node = True
    coord = ("forest", 0, 0, 0)


def test_load_objects_survives_registration_during_resolve(global_test_env, monkeypatch):
    """INTENT: resolving relations must not crash when a hook registers new
    objects (lazy NodeHandler construction registers nodes); today the live
    dict is iterated -> RuntimeError -> FAIL."""
    obj = Object.create(None, "wanderer")
    obj.location = _FakeNode()
    save_objects()

    registered = []

    class _FakeNodeHandler:
        def __init__(self):
            node = Object.create(None, "node01")
            registered.append(node.id)

        def get_node(self, loc):
            return None

    monkeypatch.setattr(
        "atheriz.objects.base_obj.get_node_handler", lambda: _FakeNodeHandler()
    )

    load_objects()

    assert registered, "fake node handler never ran during relation resolution"
    for node_id in registered:
        assert get(node_id), f"object registered during resolve vanished: {node_id}"


def test_load_objects_survives_removal_during_resolve(global_test_env, monkeypatch):
    """INTENT: hooks may also remove objects mid-pass (e.g. cleanup on load);
    iterating a snapshot must tolerate that too."""
    victim = Object.create(None, "doomed")
    victim.location = _FakeNode()
    survivor = Object.create(None, "survivor")
    save_objects()

    class _FakeNodeHandler:
        def __init__(self):
            from atheriz.globals.objects import remove_object

            remove_object(victim)

        def get_node(self, loc):
            return None

    monkeypatch.setattr(
        "atheriz.objects.base_obj.get_node_handler", lambda: _FakeNodeHandler()
    )

    load_objects()
    assert get(survivor.id), "unrelated object lost during load"
