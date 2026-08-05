"""
Auto-generate the Atheriz documentation.

This script writes the following files into the ``docs/`` directory:

- ``README.md``            - table of contents
- ``table_of_contents.md`` - table of contents (same content, kept in sync)
- ``14_api_reference.md``  - auto-generated API reference

It is a purely static, dependency-free generator: it parses the Python sources
under ``atheriz/`` with :mod:`ast` and never executes them, so it is safe to run
in any environment (no game folder, no installed deps).

Usage::

    python generate_api.py            # (re)generate all three files
    python generate_api.py --check    # verify files are up to date (exit 1 if not)
    python generate_api.py [DIR]      # write outputs into DIR (default: ./docs)
"""

import ast
import os
import sys

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
# The atheriz source tree is always the parent of this script's directory,
# regardless of where the output files are written.
BASE_DIR = os.path.dirname(DOCS_DIR)

# (number, filename, title, description)
CHAPTERS = [
    ("01", "01_getting_started.md", "Getting Started",
     "Overview, installation instructions, and how to initialize a new game folder."),
    ("02", "02_core_concepts.md", "Core Concepts",
     "Fundamental entities: Objects, Nodes (Rooms), Accounts, and Channels."),
    ("03", "03_command_system.md", "The Command System",
     "Writing commands, argument parsing, input permissions, and CmdSets."),
    ("04", "04_scripts_and_hooks.md", "Scripts & the Hook System",
     "Attaching reusable logic scripts and utilizing hook decorators."),
    ("05", "05_persistence.md", "Persistence & Serialization",
     "SQLite database architecture, custom object pickling, and relation resolution."),
    ("06", "06_settings.md", "Settings & Configuration",
     "System configuration overrides and the Class Injection mechanism."),
    ("07", "07_mixins.md", "Mixins",
     "Utilizing Flags, modifying Access restrictions, and adding custom DbOps."),
    ("08", "08_input_handling.md", "Input Handling",
     "WebSocket connections, JSON message schemas, and creating custom input functions."),
    ("09", "09_time_system.md", "The Time System",
     "Managing the game clock, responding to solar/lunar events, and scheduling alarms."),
    ("10", "10_utilities_advanced.md", "Utility Functions & Advanced Topics",
     "Math/Map utilities, string formatters, FuncParser logic, and the hot-reloader."),
    ("11", "11_async_threadpool.md", "The AsyncThreadPool",
     "Understanding concurrency, worker threads, and fire-and-forget execution."),
    ("12", "12_webclient.md", "The Webclient",
     'Internal "colon" commands and the server-to-client WebSocket protocol.'),
    ("13", "13_menu_engine.md", "The Menu Engine",
     "Creating interactive text menus using MenuEngine, Nodes, Choices, and Context."),
    ("14", "14_api_reference.md", "API Reference",
     "Auto-generated documentation outlining public classes, methods, and functions."),
    ("15", "15_sound_propagation.md", "Sound Propagation",
     "Acoustic system, BFS room traversal, loudness attenuation, and hooks for emitting and hearing sounds."),
]

# (section number, module name, classes to document; [] = all public classes)
API_TARGETS = [
    ("14.1", "atheriz.objects.base_obj", []),
    ("14.2", "atheriz.objects.nodes", []),
    ("14.3", "atheriz.objects.base_account", []),
    ("14.4", "atheriz.objects.base_channel", []),
    ("14.5", "atheriz.objects.base_script", []),
    ("14.6", "atheriz.commands.base_cmd", []),
    ("14.7", "atheriz.commands.base_cmdset", []),
    ("14.8", "atheriz.inputfuncs", []),
    ("14.9", "atheriz.globals.objects", []),
    ("14.10", "atheriz.globals.map", []),
    ("14.11", "atheriz.globals.time", []),
    ("14.12", "atheriz.utils", []),
    ("14.13", "atheriz.objects.funcparser", []),
    ("14.14", "atheriz.settings", []),
]

# Modules whose uppercase constants should also be documented.
CONSTANT_MODULES = ("atheriz.settings", "atheriz.globals.time")


def _safe_unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def _format_arg(arg) -> str:
    text = arg.arg
    if arg.annotation is not None:
        text += f": {_safe_unparse(arg.annotation)}"
    return text


def _format_arg_with_default(arg, default) -> str:
    text = _format_arg(arg)
    if default is not None:
        text += f" = {_safe_unparse(default)}"
    return text


def _format_args(args_node) -> str:
    """Render an ``arguments`` node as a Python-like signature.

    Handles positional-only args (``/``), defaults, annotations, ``*args``,
    keyword-only args, and ``**kwargs`` in the correct order.
    """
    positional = list(args_node.posonlyargs) + list(args_node.args)
    defaults = args_node.defaults
    offset = len(defaults) - len(positional)

    parts = []
    for i, arg in enumerate(positional):
        if i == len(args_node.posonlyargs) and args_node.posonlyargs:
            parts.append("/")
        default = None
        di = offset + i
        if 0 <= di < len(defaults):
            default = defaults[di]
        parts.append(_format_arg_with_default(arg, default))

    if args_node.vararg is not None:
        parts.append(f"*{_format_arg(args_node.vararg)}")

    for i, arg in enumerate(args_node.kwonlyargs):
        default = None
        if i < len(args_node.kw_defaults):
            default = args_node.kw_defaults[i]
        parts.append(_format_arg_with_default(arg, default))

    if args_node.kwarg is not None:
        parts.append(f"**{_format_arg(args_node.kwarg)}")

    return "(" + ", ".join(parts) + ")"


def _method_kind(node):
    """Return the decorator-based rendering prefix for a method node."""
    is_property = is_setter = is_classmethod = is_staticmethod = False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            is_property = True
        elif isinstance(dec, ast.Attribute) and dec.attr == "setter":
            is_setter = True
        elif isinstance(dec, ast.Name) and dec.id == "classmethod":
            is_classmethod = True
        elif isinstance(dec, ast.Name) and dec.id == "staticmethod":
            is_staticmethod = True
    if is_property:
        return "@property "
    if is_setter:
        return f"@{node.name}.setter "
    if is_classmethod:
        return "@classmethod "
    if is_staticmethod:
        return "@staticmethod "
    return ""


def _is_async(node) -> str:
    return "async " if isinstance(node, ast.AsyncFunctionDef) else ""


def _push_doc(output, doc):
    if doc:
        output.append(doc)
        output.append("")


def _assign_targets(node):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                yield target.id
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        yield node.target.id


def _doc_attr(output, name, value):
    output.append(f"#### `{name}`")
    output.append("")
    if value is not None:
        rendered = _safe_unparse(value)
        if len(rendered) > 60:
            rendered = rendered[:57] + "..."
        output.append(f"Default value: `{rendered}`")
        output.append("")


def _doc_method(output, node):
    prefix = _method_kind(node)
    signature = _format_args(node.args)
    output.append(f"#### `{prefix}{_is_async(node)}def {node.name}{signature}`")
    output.append("")
    _push_doc(output, ast.get_docstring(node))


def _doc_class(output, cls_node):
    output.append(f"### Class: `{cls_node.name}`")
    output.append("")
    _push_doc(output, ast.get_docstring(cls_node))

    for node in cls_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("__"):
                _doc_method(output, node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for name in _assign_targets(node):
                if not name.startswith("_"):
                    _doc_attr(output, name, node.value)


def _doc_function(output, node):
    signature = _format_args(node.args)
    output.append(f"### `{_is_async(node)}def {node.name}{signature}`")
    output.append("")
    _push_doc(output, ast.get_docstring(node))


def _doc_constants(output, assigns):
    for node in assigns:
        value = node.value
        for name in _assign_targets(node):
            if name.isupper() and not name.startswith("_"):
                output.append(f"### `{name}`")
                output.append("")
                if value is not None:
                    output.append(f"Default value: `{_safe_unparse(value)}`")
                    output.append("")


def _doc_module(output, tree, module_name, classes_to_document):
    _push_doc(output, ast.get_docstring(tree))

    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    ]
    assigns = [node for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))]

    if classes_to_document:
        class_names = []
        for name in classes_to_document:
            if name in classes:
                class_names.append(name)
            else:
                print(f"Class not found in {module_name}: {name}", file=sys.stderr)
    else:
        class_names = [name for name in classes if not name.startswith("_")]

    for name in class_names:
        _doc_class(output, classes[name])

    for func in functions:
        _doc_function(output, func)

    if module_name in CONSTANT_MODULES:
        _doc_constants(output, assigns)


def _toc_lines():
    lines = [
        "# Atheriz Documentation - Table of Contents",
        "",
        "Welcome to the Atheriz documentation. Atheriz is a Python framework built for creating multiplayer text-based games.",
        "",
    ]
    for i, (num, filename, title, desc) in enumerate(CHAPTERS, start=1):
        lines.append(f"{i}. **[{num} {title}](./{filename})**  ")
        lines.append(f"    *{desc}*")
    return "\n".join(lines) + "\n"


def _api_footer():
    previous = nxt = None
    for i, (num, filename, title, _desc) in enumerate(CHAPTERS):
        if num == "14":
            if i > 0:
                previous = CHAPTERS[i - 1]
            if i + 1 < len(CHAPTERS):
                nxt = CHAPTERS[i + 1]
            break
    parts = []
    if previous:
        parts.append(f"[Previous: {previous[0]} {previous[2]}](./{previous[1]})")
    parts.append("[Table of Contents](./table_of_contents.md)")
    if nxt:
        parts.append(f"[Next: {nxt[0]} {nxt[2]}](./{nxt[1]})")
    return " | ".join(parts)


def _api_reference():
    output = [
        "# 14 API Reference",
        "",
        "[Table of Contents](./table_of_contents.md)",
        "",
        "This document provides an auto-generated reference for the public classes, methods, and functions within Atheriz. It is generated by `docs/generate_api.py` - do not edit by hand.",
        "",
    ]

    for section_num, module_name, classes_to_document in API_TARGETS:
        file_path = os.path.join(BASE_DIR, module_name.replace(".", os.sep) + ".py")
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}", file=sys.stderr)
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}", file=sys.stderr)
            continue

        output.append(f"## {section_num} `{module_name}`")
        output.append("")
        _doc_module(output, tree, module_name, classes_to_document)

    output.append(_api_footer())
    output.append("")
    return "\n".join(output) + "\n"


def generate(output_dir=None):
    """Generate all documentation files; return {path: content}."""
    output_dir = output_dir or DOCS_DIR
    toc = _toc_lines()
    api = _api_reference()
    files = {
        "README.md": toc,
        "table_of_contents.md": toc,
        "14_api_reference.md": api,
    }
    return {os.path.join(output_dir, name): content for name, content in files.items()}


def main(argv=None):
    args = list(argv) if argv is not None else sys.argv[1:]
    check = "--check" in args
    positional = [a for a in args if a != "--check"]
    output_dir = positional[0] if positional else DOCS_DIR

    files = generate(output_dir)

    if check:
        ok = True
        for path, content in files.items():
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    existing = f.read()
                if existing != content:
                    ok = False
                    print(f"OUTDATED: {path}")
            else:
                ok = False
                print(f"MISSING: {path}")
        return 0 if ok else 1

    for path, content in files.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Successfully generated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
