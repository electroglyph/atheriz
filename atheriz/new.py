"""
Template generation for new game folders.

This module provides functionality to create a new game folder with template classes
that inherit from the base atheriz classes.
"""

import inspect
from pathlib import Path
from typing import Any, Callable


class ClassInspector:
    """Inspects a class to extract methods meant to be overridden."""

    def __init__(self, cls: type):
        self.cls = cls

    def get_override_methods(self) -> list[tuple[str, Any, str | None, bool]]:
        """
        Get all methods that are meant to be overridden.

        Returns:
            List of tuples: (method_name, signature, docstring, is_empty)
        """
        from atheriz.utils import get_class_hooks
        return get_class_hooks(self.cls)


class TemplateGenerator:
    """Generates Python source code for template classes."""

    def __init__(self, class_name: str, base_import: str, base_class: str):
        """
        Args:
            class_name: Name of the new class
            base_import: Full import path (e.g., "atheriz.objects.base_account")
            base_class: Name of the base class to import (e.g., "Account")
        """
        self.class_name = class_name
        self.base_import = base_import
        self.base_class = base_class
        self.methods: list[tuple[str, Any, str | None, bool]] = []
        self.extra_imports: list[str] = []
        self.add_flags: bool = False
        self.add_db_ops: bool = False
        self.add_access_lock: bool = False


    def add_methods(self, methods: list[tuple[str, Any, str | None, bool]]):
        """Add methods to generate stubs for."""
        self.methods = methods

    def _format_signature(self, name: str, sig: Any) -> str:
        """Format a method signature for the template."""
        if sig is None:
            # Fallback if signature couldn't be inspected
            return f"def {name}(self, *args, **kwargs):"

        params = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                params.append("self")
            elif param.default is inspect.Parameter.empty:
                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    params.append(f"*{param_name}")
                elif param.kind == inspect.Parameter.VAR_KEYWORD:
                    params.append(f"**{param_name}")
                else:
                    params.append(param_name)
            else:
                # Has default value
                default = param.default
                if isinstance(default, str):
                    params.append(f'{param_name}="{default}"')
                elif default is None:
                    params.append(f"{param_name}=None")
                else:
                    params.append(f"{param_name}={default!r}")

        return f"def {name}({', '.join(params)}):"

    def _format_body(self, name: str, sig: Any, is_empty: bool) -> str:
        """Format the method body."""
        if is_empty:
            return "        pass"

        if sig is None:
            return f"        return super().{name}(*args, **kwargs)"

        args = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                args.append(f"*{param_name}")
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                args.append(f"**{param_name}")
            elif param.kind == inspect.Parameter.KEYWORD_ONLY:
                args.append(f"{param_name}={param_name}")
            else:
                args.append(param_name)

        return f"        return super().{name}({', '.join(args)})"

    def generate(self) -> str:
        """Generate the complete template file content."""
        import_list = [f"{self.base_class} as Base{self.base_class}"]
        if self.extra_imports:
            import_list.extend(self.extra_imports)
            
        lines = [
            f"from {self.base_import} import {', '.join(import_list)}",
        ]
        
        if self.add_flags:
            lines.append("from .flags import Flags")
        if self.add_db_ops:
            lines.append("from .db_ops import DbOps")
        if self.add_access_lock:
            lines.append("from .access import AccessLock")

        lines.extend([
            "",
            "",
            f"class {self.class_name}(Base{self.base_class}{', Flags' if self.add_flags else ''}{', DbOps' if self.add_db_ops else ''}{', AccessLock' if self.add_access_lock else ''}):",
            f'    """Custom {self.class_name} class. Override methods below to customize behavior."""',
        ])
        
        has_methods = bool(self.methods)
        
        if self.add_flags:
            lines.extend([
                "",
                "    def __init__(self, *args, **kwargs):",
                "        super().__init__(*args, **kwargs)",
            ])
            has_methods = True

        if not has_methods:
            lines.append("    pass")
        else:
            for name, sig, doc, is_empty in self.methods:
                lines.append("")
                lines.append(f"    {self._format_signature(name, sig)}")
                if doc:
                    # Use first line of docstring only
                    first_line = doc.split("\n")[0].strip()
                    if first_line:
                        lines.append(f'        """{first_line}"""')
                lines.append(self._format_body(name, sig, is_empty))

        lines.append("")
        return "\n".join(lines)


def generate_settings_template() -> str:
    """Generate the settings.py template."""
    return '''# Import all settings from the base game
from atheriz.settings import *

# Custom settings - add or override below
# Example:
# SERVERNAME = "My Custom Game"
# WEBSERVER_PORT = 8001

# Class injection configuration
# (local_module, class_name, target_import_path)
# Class injection configuration
# (local_module, class_name, target_import_path)
CLASS_INJECTIONS = [
    ("account", "Account", "atheriz.objects.base_account"),
    ("object", "Object", "atheriz.objects.base_obj"),
    ("channel", "Channel", "atheriz.objects.base_channel"),
    ("node", "Node", "atheriz.objects.nodes"),
    ("commands.loggedin", "LoggedinCmdSet", "atheriz.commands.loggedin.cmdset"),
    ("commands.unloggedin", "UnloggedinCmdSet", "atheriz.commands.unloggedin.cmdset"),
    ("inputfuncs", "InputFuncs", "atheriz.inputfuncs"),
    ("script", "Script", "atheriz.objects.base_script"),
]

'''


def generate_module_wrapper_template(module_path: str) -> str:
    """
    Generate a thin wrapper template for a module by inspecting it dynamically.

    Discovers all public symbols (functions, classes, constants) and generates
    re-export imports plus commented-out override examples for each function.

    Args:
        module_path: Dotted import path, e.g. "atheriz.singletons.objects"
    """
    import importlib
    import types

    module = importlib.import_module(module_path)

    # Collect public names grouped by kind
    functions: list[str] = []
    classes: list[str] = []
    constants: list[str] = []

    for name in sorted(dir(module)):
        if name.startswith("_"):
            continue
        obj = getattr(module, name)
        # Skip module objects (e.g. imported 'os', 'dill', 'sqlite3')
        if isinstance(obj, types.ModuleType):
            continue
        # For callables and classes, only include if defined in THIS module
        if hasattr(obj, "__module__") and obj.__module__ is not None:
            if obj.__module__ != module_path:
                continue
        # Skip re-exported constants like TYPE_CHECKING
        if name == "TYPE_CHECKING":
            continue
        if isinstance(obj, type):
            classes.append(name)
        elif callable(obj):
            functions.append(name)
        else:
            constants.append(name)

    all_names = classes + functions + constants
    if not all_names:
        return f"# Wrapper for {module_path} (no public symbols found)\n"

    lines = [
        f"# Re-export everything from {module_path}.",
        "# Override or extend functions below to customize behavior.",
        f"from {module_path} import (  # noqa: F401",
    ]
    for name in all_names:
        lines.append(f"    {name},")
    lines.append(")")

    # Generate commented-out override examples for each function
    for func_name in functions:
        func = getattr(module, func_name)
        try:
            sig = inspect.signature(func)
            param_str = ", ".join(sig.parameters.keys())
            arg_str = ", ".join(
                f"*{p}" if sig.parameters[p].kind == inspect.Parameter.VAR_POSITIONAL
                else f"**{p}" if sig.parameters[p].kind == inspect.Parameter.VAR_KEYWORD
                else p
                for p in sig.parameters
            )
        except (ValueError, TypeError, NameError):
            param_str = "*args, **kwargs"
            arg_str = "*args, **kwargs"

        lines.append("")
        lines.append(f"# def {func_name}({param_str}):")
        lines.append(f"#     from {module_path} import {func_name} as _base_{func_name}")
        lines.append(f"#     return _base_{func_name}({arg_str})")

    lines.append("")
    return "\n".join(lines) + "\n"


def generate_objects_template() -> str:
    """Generate the objects.py template (thin wrapper around atheriz.singletons.objects)."""
    return generate_module_wrapper_template("atheriz.singletons.objects")


def generate_database_setup_template() -> str:
    """Generate the database_setup.py template (thin wrapper around atheriz.database_setup)."""
    return generate_module_wrapper_template("atheriz.database_setup")


def generate_inputfuncs_template() -> str:
    """Generate the inputfuncs.py template by inspecting InputFuncs class."""
    from atheriz.inputfuncs import InputFuncs

    inspector = ClassInspector(InputFuncs)
    methods = inspector.get_override_methods()

    generator = TemplateGenerator("InputFuncs", "atheriz.inputfuncs", "InputFuncs")
    generator.add_methods(methods)

    content = generator.generate()
    # Add inputfunc decorator import
    content = content.replace(
        "from atheriz.inputfuncs import InputFuncs",
        "from atheriz.inputfuncs import InputFuncs",
    )
    # Append usage example
    content += """
# To add a custom input handler, use the @inputfunc decorator:
# from atheriz.inputfuncs import inputfunc
#
# @inputfunc()
# def my_custom_handler(self, connection, args, kwargs):
#     \"\"\"Handle 'my_custom_handler' messages from client.\"\"\"
#     pass
"""
    return content


def generate_command_base_template() -> str:
    """Generate the commands/command.py template by inspecting Command class."""
    from atheriz.commands.base_cmd import Command

    inspector = ClassInspector(Command)
    methods = inspector.get_override_methods()

    generator = TemplateGenerator("Command", "atheriz.commands.base_cmd", "Command")
    generator.add_methods(methods)

    return generator.generate()


def generate_command_template() -> str:
    """Generate the command.py template with class attributes (scaffolding for new commands)."""
    return '''from .command import Command


class MyCommand(Command):
    """Custom Command class. Override methods below to customize behavior."""

    key = "mycommand"
    aliases = []
    desc = "A custom command"
    category = "Custom"

    def setup_parser(self):
        """Add arguments to the parser here."""
        pass

    def run(self, caller, args):
        """Implement command logic here."""
        pass
'''


def generate_loggedin_cmdset_template() -> str:
    """Generate the commands/loggedin.py template by inspecting LoggedinCmdSet class."""
    from atheriz.commands.loggedin.cmdset import LoggedinCmdSet

    inspector = ClassInspector(LoggedinCmdSet)
    methods = inspector.get_override_methods()

    generator = TemplateGenerator("LoggedinCmdSet", "atheriz.commands.loggedin.cmdset", "LoggedinCmdSet")
    generator.add_methods(methods)

    content = generator.generate()
    # Add TestCommand import after the first import line
    lines = content.split("\n")
    lines.insert(1, "from .test import TestCommand")
    content = "\n".join(lines)
    # Replace 'pass' with __init__ that registers TestCommand
    init_body = "\n".join([
        "    def __init__(self):",
        "        super().__init__()",
        "        self.add(TestCommand())",
    ])
    content = content.replace("    pass", init_body)
    return content


def generate_unloggedin_cmdset_template() -> str:
    """Generate the commands/unloggedin.py template by inspecting UnloggedinCmdSet class."""
    from atheriz.commands.unloggedin.cmdset import UnloggedinCmdSet

    inspector = ClassInspector(UnloggedinCmdSet)
    methods = inspector.get_override_methods()

    generator = TemplateGenerator("UnloggedinCmdSet", "atheriz.commands.unloggedin.cmdset", "UnloggedinCmdSet")
    generator.add_methods(methods)

    content = generator.generate()
    # Replace 'pass' with __init__ with commented example
    init_body = "\n".join([
        "    def __init__(self):",
        "        super().__init__()",
        "        # self.add(MyUnloggedinCommand())",
    ])
    content = content.replace("    pass", init_body)
    return content


def generate_test_command_template() -> str:
    """Generate the commands/test.py template (scaffolding for a test command)."""
    return '''from atheriz.commands.base_cmd import Command


class TestCommand(Command):
    """
    A simple test command to verify custom commands work.
    """
    key = "test"
    desc = "A simple test command."
    category = "Custom"

    def run(self, caller, args):
        caller.msg("test!")
'''


# Template configurations: (filename, base_import, base_class)
TEMPLATE_CONFIGS = [
    ("account.py", "atheriz.objects.base_account", "Account"),
    ("channel.py", "atheriz.objects.base_channel", "Channel"),
    ("object.py", "atheriz.objects.base_obj", "Object"),
    ("node.py", "atheriz.objects.nodes", "Node"),
    ("script.py", "atheriz.objects.base_script", "Script"),
]



def create_game_folder(folder_name: str) -> None:
    """
    Create a new game folder with template classes and initial world setup.

    Args:
        folder_name: Name of the folder to create
    """
    import os
    import getpass

    folder_path = Path(folder_name)

    if folder_path.exists():
        print(f"Error: Folder '{folder_name}' already exists.")
        return

    # Get superuser credentials from env or prompt
    username = os.environ.get("ATHERIZ_SUPERUSER_USERNAME")
    if not username:
        username = input("Enter superuser username: ").strip()
        if not username:
            print("Error: Username cannot be empty.")
            return

    password = os.environ.get("ATHERIZ_SUPERUSER_PASSWORD")
    if not password:
        password = getpass.getpass("Enter superuser password: ")
        if not password:
            print("Error: Password cannot be empty.")
            return

    print(f"Creating game folder: {folder_name}")
    folder_path.mkdir(parents=True)

    # Create __init__.py
    init_file = folder_path / "__init__.py"
    init_file.write_text("")

    # Generate template files that need class inspection
    for filename, base_import, base_class in TEMPLATE_CONFIGS:
        print(f"  Creating {filename}...")

        # Import the base class
        module = __import__(base_import, fromlist=[base_class])
        cls = getattr(module, base_class)

        # Inspect and generate
        inspector = ClassInspector(cls)
        methods = inspector.get_override_methods()

        generator = TemplateGenerator(base_class, base_import, base_class)
        generator.add_flags = True
        generator.add_db_ops = True
        if base_class in ("Object", "Node", "Channel"):
            generator.add_access_lock = True
        
        if base_class == "Script":
            generator.extra_imports = ["before", "after", "replace"]
            
        generator.add_methods(methods)


        content = generator.generate()
        (folder_path / filename).write_text(content)

    # Generate special templates
    print("  Creating flags.py...")
    import atheriz.objects.base_flags
    flags_src = Path(atheriz.objects.base_flags.__file__)
    (folder_path / "flags.py").write_text(flags_src.read_text())

    print("  Creating db_ops.py...")
    import atheriz.objects.base_db_ops
    db_ops_src = Path(atheriz.objects.base_db_ops.__file__)
    (folder_path / "db_ops.py").write_text(db_ops_src.read_text())

    print("  Creating access.py...")
    import atheriz.objects.base_lock
    access_src = Path(atheriz.objects.base_lock.__file__)
    (folder_path / "access.py").write_text(access_src.read_text())

    # Create commands directory
    print("  Creating commands directory...")
    commands_path = folder_path / "commands"
    commands_path.mkdir(parents=True)
    (commands_path / "__init__.py").write_text("")

    print("  Creating commands/command.py...")
    (commands_path / "command.py").write_text(generate_command_base_template())

    print("  Creating commands/test.py...")
    (commands_path / "test.py").write_text(generate_test_command_template())

    print("  Creating commands/loggedin.py...")
    (commands_path / "loggedin.py").write_text(generate_loggedin_cmdset_template())

    print("  Creating commands/unloggedin.py...")
    (commands_path / "unloggedin.py").write_text(generate_unloggedin_cmdset_template())

    print("  Creating inputfuncs.py...")
    (folder_path / "inputfuncs.py").write_text(generate_inputfuncs_template())

    print(f"  Creating settings.py...")
    (folder_path / "settings.py").write_text(generate_settings_template())

    print("  Creating objects.py...")
    (folder_path / "objects.py").write_text(generate_objects_template())

    print("  Creating database_setup.py...")
    (folder_path / "database_setup.py").write_text(generate_database_setup_template())

    # Copy initial_setup.py
    print(f"  Copying initial_setup.py...")
    import atheriz.initial_setup
    initial_setup_src = Path(atheriz.initial_setup.__file__)
    content = initial_setup_src.read_text()
    
    # Patch imports to use local template classes
    content = content.replace(
        "from atheriz.objects.base_account import Account",
        "from .account import Account"
    )
    content = content.replace(
        "from atheriz.objects.base_obj import Object",
        "from .object import Object"
    )
    content = content.replace(
        "from atheriz.objects.base_channel import Channel",
        "from .channel import Channel"
    )
    content = content.replace(
        "from atheriz.objects.nodes import Node, NodeGrid, NodeArea, NodeLink",
        "from .node import Node\nfrom atheriz.objects.nodes import NodeGrid, NodeArea, NodeLink"
    )
    content = content.replace(
        "from atheriz.commands.base_cmd import Command",
        "from .commands.command import Command"
    )
    content = content.replace(
        "from atheriz.singletons.objects import add_object, save_objects",
        "from .objects import add_object, save_objects"
    )
    content = content.replace(
        "from atheriz.database_setup import do_setup as do_db_setup",
        "from .database_setup import do_setup as do_db_setup"
    )


    
    (folder_path / "initial_setup.py").write_text(content)

    # Copy connection_screen.py
    print(f"  Copying connection_screen.py...")
    import atheriz.connection_screen
    connection_screen_src = Path(atheriz.connection_screen.__file__)
    (folder_path / "connection_screen.py").write_text(connection_screen_src.read_text())

    # Copy server_events.py
    print(f"  Copying server_events.py...")
    import atheriz.server_events
    server_events_src = Path(atheriz.server_events.__file__)
    (folder_path / "server_events.py").write_text(server_events_src.read_text())

    # Copy web folder (templates + static files)
    print(f"  Copying web folder...")
    import shutil
    web_src = Path(__file__).parent / "web"
    if web_src.exists():
        shutil.copytree(web_src, folder_path / "web")
    else:
        print(f"  Warning: Web folder not found at {web_src}")

    # Create save directory in the game folder
    save_path = folder_path / "save"
    save_path.mkdir(parents=True)

    # Set up initial world and superuser account
    print("\nSetting up initial world state...")

    # Set up sys.path to include the parent of the new game folder
    # This allows importing the game folder as a package for relative imports
    import sys
    import importlib
    parent_dir = str(folder_path.parent.resolve())
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    pkg_name = folder_path.name

    # Import settings to configure paths
    game_settings = importlib.import_module(f"{pkg_name}.settings")

    
    # Override save path keys in the global settings to match the new game folder
    import atheriz.settings as global_settings
    global_settings.SAVE_PATH = str(save_path.resolve())
    
    secret_path = folder_path / "secret"
    secret_path.mkdir(parents=True, exist_ok=True)
    global_settings.SECRET_PATH = str(secret_path.resolve())


    # Import and run initial_setup from the new game folder as a package
    try:
        local_setup = importlib.import_module(f"{pkg_name}.initial_setup")
        local_setup.do_setup(username, password)

    except Exception as e:
        print(f"Error during initial setup: {e}")
        import traceback
        traceback.print_exc()
        return
     
    print(f"\nSuccess! Game folder '{folder_name}' created with:")
    print(f"  Template files:")
    print(f"    - account.py, channel.py, object.py, node.py")
    print(f"    - script.py, flags.py, access.py, objects.py, database_setup.py")
    print(f"    - commands/, inputfuncs.py, settings.py")
    print(f"    - initial_setup.py, connection_screen.py")
    print(f"    - web/ (templates and static files)")
    print(f"  Initial world:")
    print(f"    - Superuser account: {username}")
    print(f"    - Starting room at {game_settings.DEFAULT_HOME}")
