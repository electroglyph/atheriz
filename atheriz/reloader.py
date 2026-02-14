import sys
import importlib
import os
from pathlib import Path
from typing import Any
import types
from atheriz.singletons.objects import _ALL_OBJECTS, _ALL_OBJECTS_LOCK, filter_by

# Core modules that should never be reloaded (would break server state)
_EXCLUDED_MODULES = {
    "atheriz.atheriz",
    "atheriz.reloader",
    "atheriz.websocket",
    "atheriz.singletons.get",
    "atheriz.singletons.objects",
}


def _get_atheriz_package_dir() -> Path:
    """Get the atheriz package directory. Uses __path__ since __file__ is None for editable installs."""
    import atheriz
    return Path(list(atheriz.__path__)[0]).resolve()


def _discover_new_atheriz_modules():
    """
    Walk the atheriz package directory and import any .py files that
    aren't already in sys.modules. This ensures new files (e.g. a newly
    added command) are picked up on reload.
    """
    package_dir = _get_atheriz_package_dir()
    discovered = 0

    for root, dirs, files in os.walk(package_dir):
        # skip __pycache__, hidden folders, and tests
        dirs[:] = [d for d in dirs if not d.startswith(("__", ".")) and d != "tests"]

        for filename in files:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = Path(root) / filename
            # Convert file path to module name: atheriz.commands.loggedin.map
            rel = filepath.relative_to(package_dir)
            parts = list(rel.with_suffix("").parts)
            module_name = "atheriz." + ".".join(parts)

            if module_name in sys.modules or module_name in _EXCLUDED_MODULES:
                continue

            try:
                importlib.import_module(module_name)
                discovered += 1
            except Exception as e:
                print(f"[HotReload] Could not import new module {module_name}: {e}")

    return discovered


def _discover_new_game_modules():
    """
    Walk the game folder (CWD) and import any .py files that aren't
    already in sys.modules. This ensures new files added by users
    (e.g. new commands) are picked up on reload.
    """
    cwd = Path.cwd().resolve()
    atheriz_dir = str(_get_atheriz_package_dir())

    discovered = 0

    for root, dirs, files in os.walk(cwd):
        # At the top level, only descend into directories that are Python packages
        if Path(root).resolve() == cwd:
            dirs[:] = [d for d in dirs if (Path(root) / d / "__init__.py").exists()]
        else:
            dirs[:] = [d for d in dirs if d != "__pycache__"]

        # Don't walk into the atheriz package itself
        if str(Path(root).resolve()).startswith(atheriz_dir):
            continue

        for filename in files:
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = Path(root) / filename
            # Convert file path to module name relative to CWD
            rel = filepath.relative_to(cwd)
            parts = list(rel.with_suffix("").parts)
            module_name = ".".join(parts)

            if module_name in sys.modules:
                continue

            try:
                importlib.import_module(module_name)
                discovered += 1
            except Exception as e:
                print(f"[HotReload] Could not import new game module {module_name}: {e}")

    return discovered


def _reload_game_folder_modules():
    """
    Discover new game folder modules, reload all game folder modules,
    then re-run CLASS_INJECTIONS so that overridden classes are
    re-applied to their target modules.
    """
    from atheriz import settings

    # Step 1: Discover new game folder modules from disk
    new_count = _discover_new_game_modules()
    if new_count:
        print(f"[HotReload] Discovered {new_count} new game module(s).")

    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)
    atheriz_dir = str(_get_atheriz_package_dir())

    # Only consider top-level subdirectories that are Python packages
    valid_packages = {str(cwd / d) for d in os.listdir(cwd)
                      if (cwd / d).is_dir() and (cwd / d / "__init__.py").exists()}

    game_modules = []
    for module_name, module in list(sys.modules.items()):
        mod_file = getattr(module, "__file__", None)
        if not mod_file:
            continue
        mod_path = str(Path(mod_file).resolve())
        # Module is in the game folder (CWD) but NOT part of the atheriz package
        if mod_path.startswith(cwd_str) and not mod_path.startswith(atheriz_dir):
            # Must be inside a top-level directory that has __init__.py
            if not any(mod_path.startswith(pkg) for pkg in valid_packages):
                continue
            game_modules.append((module_name, module))

    # Sort so dependencies come before dependents (e.g. test.py before loggedin.py)
    game_modules.sort(key=lambda x: (x[0].count("."), x[0]))

    reloaded = 0
    errors = []
    for module_name, module in game_modules:
        try:
            importlib.reload(module)
            reloaded += 1
        except Exception as e:
            msg = f"Failed to reload game module {module_name}: {e}"
            print(f"[HotReload] {msg}")
            errors.append(msg)

    # Re-run class injections so game folder overrides take effect
    injections = getattr(settings, "CLASS_INJECTIONS", [])
    for local_mod, cls_name, target_mod in injections:
        try:
            if local_mod in sys.modules:
                module = sys.modules[local_mod]
            else:
                module = importlib.import_module(local_mod)

            if hasattr(module, cls_name):
                new_cls = getattr(module, cls_name)
                target = importlib.import_module(target_mod)
                setattr(target, cls_name, new_cls)
        except Exception as e:
            msg = f"Failed to re-inject {cls_name} from {local_mod}: {e}"
            print(f"[HotReload] {msg}")
            errors.append(msg)

    if reloaded:
        print(f"[HotReload] Reloaded {reloaded} game folder module(s).")

    return reloaded, errors


def reload_game_logic() -> str:
    """
    Reloads all atheriz modules (except core server logic) and patches existing objects.

    Returns:
        str: A status message describing what was done.
    """
    from atheriz.logger import logger
    logger.info("Server reload initiated.")

    # Step 0: Discover new atheriz.* modules from disk (e.g. newly added command files)
    new_count = _discover_new_atheriz_modules()
    if new_count:
        print(f"[HotReload] Discovered {new_count} new module(s) from disk.")

    modules_to_reload = []

    # Identify atheriz modules to reload
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("atheriz."):
            continue

        if module_name in _EXCLUDED_MODULES:
            continue

        if not isinstance(module, types.ModuleType):
            continue

        modules_to_reload.append((module_name, module))

    # Sort modules to attempt a somewhat reasonable order (e.g. utils before objects)
    # This is a heuristic; perfect dependency sorting is hard dynamically.
    # We move 'cmdset' modules to the end because they import all the commands in their directory,
    # and we want them to pick up the reloaded versions of those commands.
    modules_to_reload.sort(key=lambda x: (x[0].endswith(".cmdset"), x[0]))

    reloaded_count = 0
    errors = []

    print(f"[HotReload] Found {len(modules_to_reload)} atheriz modules to reload.")

    # Reload atheriz modules
    for module_name, module in modules_to_reload:
        try:
            importlib.reload(module)
            reloaded_count += 1
        except Exception as e:
            msg = f"Failed to reload {module_name}: {e}"
            print(f"[HotReload] {msg}")
            errors.append(msg)

    # Reload game folder modules and re-run class injections
    game_reloaded, game_errors = _reload_game_folder_modules()
    reloaded_count += game_reloaded
    errors.extend(game_errors)

    # Invalidate Singleton Caches
    # We DO NOT want to reset these, as it kills the game state
    # get._UNLOGGEDIN_CMDSET = None
    # get._NODE_HANDLER = None

    # Patch existing objects
    # We iterate over all live objects and try to find their new class definition
    objects_patched = 0

    def _patch_object(obj):
        nonlocal objects_patched
        try:
            # Get the module where the object's class is defined
            module_name = obj.__class__.__module__
            class_name = obj.__class__.__name__

            if module_name not in sys.modules:
                return

            module = sys.modules[module_name]

            # Get the new class definition from the reloaded module
            if hasattr(module, class_name):
                new_class = getattr(module, class_name)

                # Check if it's actually different (it should be if module was reloaded)
                if obj.__class__ is not new_class:
                    state = None
                    if hasattr(obj, "__getstate__"):
                        state = obj.__getstate__()
                    else:
                        state = obj.__dict__.copy()

                    # Capture transient state that might be lost during init/setstate
                    # session is the most critical one for logged-in players
                    saved_session = getattr(obj, "session", None)

                    obj.__class__ = new_class

                    try:
                        obj.__init__()
                    except TypeError:
                        # Fallback for classes that require arguments in __init__
                        # We can't easily guess arguments, so we skip re-init for them
                        # and just trust the class update + state restore.
                        pass

                    if hasattr(obj, "__setstate__"):
                        obj.__setstate__(state)
                    else:
                        obj.__dict__.update(state)

                    # Restore transient state
                    if saved_session:
                        obj.session = saved_session

                    objects_patched += 1
                    if hasattr(obj, "at_server_reload"):
                        obj.at_server_reload()
        except Exception as e:
            print(f"[HotReload] Error patching object {obj}: {e}")

        # Recurse into CmdSets (for Objects and Sessions)
        # We need to do this even if the object itself wasn't patched,
        # because the commands might have been reloaded.
        try:
            if hasattr(obj, "internal_cmdset") and obj.internal_cmdset:
                for cmd in list(obj.internal_cmdset.commands.values()):
                    _patch_object(cmd)
            if hasattr(obj, "external_cmdset") and obj.external_cmdset:
                for cmd in list(obj.external_cmdset.commands.values()):
                    _patch_object(cmd)
        except Exception as e:
            print(f"[HotReload] Error patching cmdsets for {obj}: {e}")

    # 2. Nodes and related structures
    try:
        # Import here to avoid potential circular imports at top level if reloader is imported early
        from atheriz.singletons.get import get_node_handler

        nh = get_node_handler()
        if nh:
            # Areas
            for area in nh.get_areas():
                _patch_object(area)
                # Grids
                for grid in area.grids.values():
                    _patch_object(grid)
                    # Nodes
                    for node in grid.nodes.values():
                        _patch_object(node)
                        # NodeLinks are inside nodes, but they are technically objects too?
                        # NodeLink is a class in nodes.py.
                        if node.links:
                            for link in node.links:
                                _patch_object(link)

            # Transitions
            for t in nh.transitions.values():
                _patch_object(t)

            # Doors
            for d_group in nh.doors.values():
                for d in d_group.values():
                    _patch_object(d)

    except Exception as e:
        msg = f"Error patching nodes: {e}"
        print(f"[HotReload] {msg}")
        errors.append(msg)

    # do channnels first so that they are available for objects to use
    channels = filter_by(lambda x: x.is_channel)
    rest = filter_by(lambda x: not x.is_channel)
    for obj in channels:
        _patch_object(obj)
    for obj in rest:
        _patch_object(obj)

    # 3. Global Command Sets
    try:
        from atheriz.singletons.get import get_loggedin_cmdset, get_unloggedin_cmdset

        global_sets = [get_loggedin_cmdset(), get_unloggedin_cmdset()]
        for s in global_sets:
            if s:
                # Patch existing commands FIRST (before __init__ replaces them)
                for cmd in list(s.commands.values()):
                    _patch_object(cmd)

                # Then patch the CmdSet class itself
                _patch_object(s)

                # Finally re-initialize (creates new command instances)
                try:
                    s.__init__()
                except Exception as e:
                    print(f"[HotReload] Error re-initializing CmdSet {s}: {e}")
    except Exception as e:
        msg = f"Error patching global cmdsets: {e}"
        print(f"[HotReload] {msg}")
        errors.append(msg)

    result_msg = (
        f"Reloaded {reloaded_count} modules. "
        f"Patched {objects_patched} objects. "
        f"Errors: {len(errors)}"
    )
    if errors:
        result_msg += f"\nFirst Error: {errors[0]}"

    print(f"[HotReload] {result_msg}")
    logger.info(f"Server reload complete: {result_msg}")
    return result_msg
