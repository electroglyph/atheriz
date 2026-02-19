import pytest
from atheriz.new import ClassInspector, TemplateGenerator

class BaseMock:
    """Base class with various hooks."""
    def at_hook_with_args(self, arg1, arg2=None):
        """Docstring for hook with args."""
        return arg1

    def at_empty_hook(self):
        """This hook is empty."""
        pass

    def at_hook_with_bad_typehint(self, x: 'UndefinedClass'):
        """This hook has a bad typehint."""
        return x

def test_hook_discovery():
    inspector = ClassInspector(BaseMock)
    methods = inspector.get_override_methods()
    
    names = [m[0] for m in methods]
    assert "at_hook_with_args" in names
    assert "at_empty_hook" in names
    assert "at_hook_with_bad_typehint" in names
    
    # Check is_empty
    empty_hook = next(m for m in methods if m[0] == "at_empty_hook")
    assert empty_hook[3] is True
    
    arg_hook = next(m for m in methods if m[0] == "at_hook_with_args")
    assert arg_hook[3] is False

def test_template_generation():
    inspector = ClassInspector(BaseMock)
    methods = inspector.get_override_methods()
    
    generator = TemplateGenerator("Mock", "mock_module", "BaseMock")
    generator.add_methods(methods)
    
    content = generator.generate()
    
    # Verify at_empty_hook has pass
    assert "def at_empty_hook(self):" in content
    assert "        pass" in content
    
    # Verify at_hook_with_args has super call
    assert "def at_hook_with_args(self, arg1, arg2=None):" in content
    assert "        return super().at_hook_with_args(arg1, arg2)" in content
    
    # Verify at_hook_with_bad_typehint is present (fallback signature)
    assert "def at_hook_with_bad_typehint" in content
