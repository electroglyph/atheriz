# 10 Utility Functions & Advanced Topics

## 10.1 Utility Functions

### 10.1.1 Color & Formatting
Atheriz provides utilities to handle terminal text formatting located in [`atheriz/utils.py`](../atheriz/utils.py):
- `wrap_xterm256(text, fg, bg, bold, italic, underline, inverse, strikethru, clear, fg_bright, ...)` (`atheriz/utils.py:98`): wraps in xterm-256 (fg `0-255`, bg, attrs).
- `wrap_truecolor(text, fg, bg, fg_bright, fg_sat, bg_bright, bg_sat, bold, ...)` (`atheriz/utils.py:145`): 24-bit RGB via HSV hue `0-360` (`fg=None`→white, `bg=0.0`→black). `120.0` ≈ green; supports `bg None`, `fg_bright/sat` etc.
- `wrap_rgb(text, fg=(r,g,b), bg=(r,g,b), ...)` (`atheriz/utils.py:217`): exact RGB tuples.
- `strip_ansi(text)`: Removes all ANSI escape codes from a string.

### 10.1.2 Dice & Math
Standard math wrappers are included in [`atheriz/utils.py`](../atheriz/utils.py):
- `dice_roll(rolls, faces)`: Simulates rolling dice.
- `dice_roll_average(rolls, faces)`: Returns the statistical average of a roll.
- `clamp(minimum, value, maximum)`: Restricts a value to a given range.

### 10.1.3 Map Utilities
Functions for spatial calculations (`atheriz/utils.py:285`):
- `get_dir(origin: tuple, dest: tuple) -> str` / `dist_3d(origin, dest)` handle both `Coord` (`area,x,y,z` 4-tuple) and plain 3-tuple; `get_dir` uses `origin[1]=x, origin[2]=y`.
- `get_reverse_link(location: Node, destination: Node) -> NodeLink|None` (`atheriz/utils.py:316`): reverse exit.

## 10.2 The FuncParser

### 10.2.1 What is FuncParser?
FuncParser evaluates inline functions embedded in strings. This is primarily used for actor-stance messaging within `Node.msg_contents()`. 

Example string: `$You() $conj(swing) the sword.`
- The actor sees: "You swing the sword."
- Third parties see: "Bob swings the sword."

The full list of available inline functions is defined in [`atheriz/objects/funcparser.py`](../atheriz/objects/funcparser.py).

## 10.3 Doors

### 10.3.1 The Door System
Doors govern access between adjacent nodes. The `Door` class defined in [`atheriz/objects/base_door.py`](../atheriz/objects/base_door.py) supports state tracking for open, closed, locked, and unlocked configurations. Map rendering settings dictate the specific ANSI characters used to represent door states visually.

## 10.4 Pathfinding

### 10.4.1 Built-in Pathfinding
`astar(start: Node, end: Node, caller: Object|None=None) -> (bool, list[Node], list[Node])` in [`atheriz/pathfind.py`](../atheriz/pathfind.py) with door-aware filtering when `caller` supplied (`door.closed/locked` + `access(caller,"open"/"unlock")` `68`) and capped by `MAX_ASTAR_ITERATIONS=50000` (`atheriz/settings.py:119`, `pathfind.py:106`).

## 10.5 The Connection Screen

### 10.5.1 Customizing the Login Screen
The text displayed before auth is `render(session=None)` in `atheriz/connection_screen.py:71` (game copy `grotto/connection_screen.py` via `atheriz/new.py:721`). It is hard-imported (`atheriz/inputfuncs.py:7` `from atheriz.connection_screen import render`), not via `CLASS_INJECTIONS` (injections handle classes only, `atheriz/atheriz.py:152`, `grotto/settings.py:25`). Override by replacing the file (reloader picks it up).

## 10.6 Server Events

### 10.6.1 `server_events.py`
`atheriz/server_events.py:8` exposes `at_server_start()`, `at_server_stop()`, `at_server_reload()`, and `at_char_create(account_name, char_name, password)` (CLI `atheriz create` hook, `19`). Game folder `grotto/server_events.py` is imported via fallback `import server_events` else `atheriz.server_events` (`atheriz/globals/startstop.py:38`); no `CLASS_INJECTIONS` needed.

## 10.7 The Hot Reloader

### 10.7.1 Code Reloading
Hot-reloader at [`atheriz/reloader.py`](../atheriz/reloader.py) triggered by `atheriz reload` (CLI → `/_internal/hot_reload`, `atheriz/atheriz.py:1159`) or in-game `reload` cmd (`commands/loggedin/reload.py:36` → `server_events.at_server_reload()`). Discovers new modules (`_discover_new_atheriz_modules:47`, `_discover_new_game_modules:82`), two-pass reload, skips `_EXCLUDED_MODULES` (`atheriz.settings`, `asyncthreadpool`, … `13`), patches live objects/cmdsets (`382`), and re-runs `setup_game_folder`. Structural inheritance/pickle changes still need full restart.

[Table of Contents](./table_of_contents.md) | [Next: 11 The AsyncThreadPool](./11_async_threadpool.md)
