import pytest
from atheriz.objects.nodes import Node
from atheriz.objects.base_script import Script, before, after, replace


class NodeDescBeforeScript(Script):
    @before
    def at_desc(self, looker=None, **kwargs):
        self.child.desc_logged = True


class NodeBlockLeaveScript(Script):
    @replace
    def at_pre_object_leave(self, destination, to_exit=None, **kwargs):
        return False


class NodeDeleteAfterScript(Script):
    @after
    def at_delete(self, caller):
        self.child.delete_logged = True
        return True  # override return value


class NodeUnmarkedScript(Script):
    def at_desc(self, looker=None, **kwargs):
        pass


class NodeTickBeforeScript(Script):
    @before
    def at_tick(self):
        self.child.tick_logged = True


def test_node_add_remove_script():
    node = Node(coord=("test_area", 0, 0, 0))
    script = NodeDescBeforeScript()
    script.id = 301

    node.add_script(script)
    assert script.id in node.scripts
    assert len(node.hooks.get("at_desc", set())) == 1

    node.remove_script(script)
    assert script.id not in node.scripts
    assert len(node.hooks.get("at_desc", set())) == 0


def test_node_at_desc_before_hook():
    node = Node(coord=("test_area", 0, 0, 0))
    script = NodeDescBeforeScript()
    script.id = 302
    node.add_script(script)

    node.at_desc(looker=None)
    assert node.desc_logged is True


def test_node_at_pre_object_leave_replace_hook():
    node = Node(coord=("test_area", 0, 0, 0))
    script = NodeBlockLeaveScript()
    script.id = 303
    node.add_script(script)

    result = node.at_pre_object_leave(destination=None)
    assert result is False


def test_node_at_delete_after_hook():
    node = Node(coord=("test_area", 0, 0, 0))
    script = NodeDeleteAfterScript()
    script.id = 304
    node.add_script(script)

    class MockCaller:
        id = 1
        name = "Mock"

        def msg(self, *args, **kwargs):
            pass

    node.access = lambda caller, lock_type: True
    result = node.at_delete(MockCaller())
    assert node.delete_logged is True
    assert result is True


def test_node_unmarked_hook_raises():
    node = Node(coord=("test_area", 0, 0, 0))
    script = NodeUnmarkedScript()
    script.id = 305
    node.add_script(script)

    with pytest.raises(ValueError) as exc:
        node.at_desc()
    assert "has hooks but none are marked" in str(exc.value)


def test_node_at_tick_before_hook():
    node = Node(coord=("test_area", 0, 0, 0))
    script = NodeTickBeforeScript()
    script.id = 306
    node.add_script(script)

    node.at_tick()
    assert node.tick_logged is True


def test_node_multiple_hooks():
    """Ensure multiple scripts can register hooks on the same node method."""
    node = Node(coord=("test_area", 0, 0, 0))
    script1 = NodeTickBeforeScript()
    script1.id = 307
    script2 = NodeTickBeforeScript()
    script2.id = 308

    node.add_script(script1)
    node.add_script(script2)

    assert len(node.hooks.get("at_tick", set())) == 2
    node.at_tick()
    assert node.tick_logged is True

    node.remove_script(script1)
    assert len(node.hooks.get("at_tick", set())) == 1
