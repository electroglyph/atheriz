"""Issue tests that need an actual `importlib.reload` cycle. They run in a
subprocess (fresh interpreter) so the reload can't corrupt the live pytest
session, then assert on `AT_RESULT key=value` lines the child prints.

Covers:
- #9  Hot-reload wipes game-folder settings: `atheriz.settings` is not in
      `_EXCLUDED_MODULES`, so `importlib.reload` re-executes it back to
      defaults and the game-folder values are never re-injected.
- #27 Script hooks unreleasable after reload: a Script whose child's class
      lives in a non-reloadable module (here `__main__`) gets patched while
      the child does not, so `resolve_relations` never restores the
      `script.child` link and `delete()` can no longer remove the hooks.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HOOKS_PY = """\
from atheriz.objects.base_script import Script, after


class HookScript(Script):
    @after
    def at_tick(self):
        pass
"""

SETTINGS_PY = 'AUTOSAVE_MINUTES = 99\nSAVE_PATH = "game_save"\n'

SETTINGS_CHILD = """\
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))

from atheriz.atheriz import setup_game_folder
setup_game_folder(required=False)

from atheriz import settings
assert settings.AUTOSAVE_MINUTES == 99, settings.AUTOSAVE_MINUTES
assert settings.SAVE_PATH == "game_save", settings.SAVE_PATH

from atheriz.reloader import reload_game_logic
reload_game_logic()

print(f"AT_RESULT autosave_minutes={settings.AUTOSAVE_MINUTES}")
print(f"AT_RESULT save_path={settings.SAVE_PATH}")
"""

HOOKS_CHILD = """\
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parent))

from atheriz import settings
settings.SAVE_PATH = str(Path.cwd() / "save")
from atheriz.database_setup import do_setup
do_setup()
from atheriz.globals.get import set_id
set_id(-1)

from atheriz.objects.base_obj import Object
from atheriz.globals.objects import add_object

pkg = Path.cwd().name
mod = __import__(f"{pkg}.hooks", fromlist=["HookScript"])
HookScript = mod.HookScript


class Room(Object):
    pass


obj = Room.create(None, "Room")
script = HookScript()
script.id = 5001
script.is_temporary = True
add_object(script)
obj.add_script(script)

assert len(obj.hooks.get("at_tick", set())) == 1, obj.hooks

from atheriz.reloader import reload_game_logic
reload_game_logic()

print(f"AT_RESULT child_preserved={script.child is not None}")

script.delete()

print(f"AT_RESULT hooks_removed={len(obj.hooks.get('at_tick', set())) == 0}")
print(f"AT_RESULT script_removed={script.id not in obj.scripts}")
"""


def _make_game_folder(tmp_path: Path) -> Path:
    """Create a minimal game folder (settings.py + hooks.py + __init__.py)."""
    gf = tmp_path / f"game{os.getpid()}"
    gf.mkdir()
    (gf / "__init__.py").write_text("")
    (gf / "settings.py").write_text(SETTINGS_PY)
    (gf / "hooks.py").write_text(HOOKS_PY)
    (gf / "save").mkdir()
    return gf


def _run_child(game_folder: Path, child: Path) -> dict[str, str]:
    proc = subprocess.run(
        [sys.executable, str(child)],
        cwd=str(game_folder),
        capture_output=True,
        text=True,
        timeout=120,
    )
    results = dict(re.findall(r"AT_RESULT (\w+)=(\S+)", proc.stdout))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return results


class TestReloadKeepsSettings:
    def test_reload_preserves_game_folder_settings(self, tmp_path):
        """INTENT: values injected by setup_game_folder must survive a
        hot-reload. Currently `atheriz.settings` is reloaded to defaults."""
        gf = _make_game_folder(tmp_path)
        child = tmp_path / "child_settings.py"
        child.write_text(SETTINGS_CHILD)

        results = _run_child(gf, child)

        assert results["autosave_minutes"] == "99"
        assert results["save_path"] == "game_save"


class TestReloadKeepsScriptHooks:
    def test_reload_keeps_script_hooks_releasable(self, tmp_path):
        """INTENT: after a reload cycle a script's child link must survive so
        `delete()` can still remove its hooks. The child's class is defined in
        `__main__` (a module the reloader cannot re-import), which is what
        leaves the script orphaned from its child."""
        gf = _make_game_folder(tmp_path)
        child = tmp_path / "child_hooks.py"
        child.write_text(HOOKS_CHILD)

        results = _run_child(gf, child)

        assert results["child_preserved"] == "True"
        assert results["hooks_removed"] == "True"
        assert results["script_removed"] == "True"
