# 01 Getting Started

## 1.1 What is Atheriz?

### 1.1.1 Overview
Atheriz is a Python framework for building multiplayer text games, such as MUDs or MUSHes. It provides built-in functionality including mapping, a robust time system, and WebSocket connectivity right out of the box. Like Evennia, it is designed specifically to be subclassed and customized, rather than forked. You write a game folder containing your custom subclasses, and the engine injects those classes at runtime.

### 1.1.2 Key Concepts at a Glance
- **Object**: The base physical entity in the game (players, NPCs, items). [Read more](./02_core_concepts.md#21-objects-object)
- **Node**: A room or map location. [Read more](./02_core_concepts.md#22-nodes-rooms)
- **Account**: The player's login credentials, distinct from characters. [Read more](./02_core_concepts.md#23-accounts)
- **Command**: A unit of action triggered by player input. [Read more](./03_command_system.md#31-how-commands-work)
- **CmdSet**: A collection of available Commands for a given state. [Read more](./03_command_system.md#33-command-sets-cmdset)
- **Script**: Reusable behaviors attached to Objects. [Read more](./04_scripts_and_hooks.md)
- **Channel**: A pub/sub communication system for players. [Read more](./02_core_concepts.md#24-channels)
- **InputFuncs**: Functions that handle incoming WebSocket messages. [Read more](./08_input_handling.md)
- **Settings**: Configuration overrides for the server. [Read more](./06_settings.md)

Atheriz utilizes a class injection system. When the server starts, it reads `CLASS_INJECTIONS` from your `settings.py` and transparently replaces its own base classes with your game's subclasses, ensuring the entire engine uses your custom rules and implementations.

## 1.2 Installation

### 1.2.1 Prerequisites

Atheriz requires Python `>=3.13` (`pyproject.toml` `requires-python`). Python 3.14t (free-threaded, `3.14t`) is highly recommended for best concurrency — when the GIL is disabled the engine forces `SLOW_LOCKS=True` (`atheriz/settings.py:143`) — but 3.13 and regular 3.14 work fine. [uv](https://docs.astral.sh/uv/getting-started/installation/) is an easy way to manage Python versions and virtual environments.

**Install uv:**
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Install Python 3.14t with uv:**
```sh
uv python install 3.14t
```

### 1.2.2 Creating a Virtual Environment

It is strongly recommended to install Atheriz inside a virtual environment to keep dependencies isolated.

**With uv (recommended):**
```sh
uv venv --python 3.14t
source .venv/bin/activate
```

**With standard Python:**
```sh
python3.14t -m venv .venv
source .venv/bin/activate
```

On Windows, replace `source .venv/bin/activate` with `.venv\Scripts\activate`.

### 1.2.3 Installing Atheriz

Atheriz is not yet published to PyPI, so install it directly from the repository:

```sh
git clone https://github.com/electroglyph/atheriz.git
cd atheriz
pip install .
```

## 1.3 Creating Your First Game

### 1.3.1 Running `atheriz new`
To start building, use the scaffold command. Navigate to an empty directory or the location where you want your game folder to reside and run:

```sh
atheriz new my_game
```

This creates a `my_game` directory containing a set of template Python files. These files provide the skeleton of an Atheriz game, subclassing the framework's default objects.

```text
my_game/
├── __init__.py
├── access.py
├── account.py
├── channel.py
├── connection_screen.py
├── database_setup.py
├── commands/
│   ├── __init__.py
│   ├── command.py
│   ├── loggedin.py
│   └── unloggedin.py
├── db_ops.py
├── door.py
├── flags.py
├── initial_setup.py
├── inputfuncs.py
├── node.py
├── object.py
├── objects.py
├── script.py
├── server_events.py
├── settings.py
└── web/
    ├── static/
    └── templates/
```

### 1.3.2 Understanding the Generated Files
Each generated file corresponds to a base class in the Atheriz framework and serves a distinct purpose:

| File | Base Class | Purpose |
|------|-----------|---------|
| `object.py` | `atheriz.objects.base_obj.Object` | Base for in-game entities (items, NPCs, PCs). |
| `account.py` | `atheriz.objects.base_account.Account` | Handles player account data and login logic. |
| `node.py` | `atheriz.objects.nodes.Node` | Represents rooms and map locations. |
| `script.py` | `atheriz.objects.base_script.Script` | Extends object behavior with scripts. |
| `channel.py` | `atheriz.objects.base_channel.Channel` | Represents communication channels. |
| `commands/command.py` | `atheriz.commands.base_cmd.Command` | The base class for custom player commands. |
| `commands/loggedin.py` | `LoggedinCmdSet` | Commands available when authenticated. |
| `commands/unloggedin.py`| `UnloggedinCmdSet`| Commands available at the login prompt. |
| `inputfuncs.py` | `atheriz.inputfuncs.InputFuncs` | Custom handles for WebSocket messages. |
| `settings.py` | `atheriz.settings` | Game configuration and class injection settings. |
| `flags.py` | `atheriz.objects.base_flags.Flags` (mixin, copy) | Boolean flags (`is_pc`, `is_item`, etc.); `Tags` helpers. Generated via `new.py:622`. |
| `access.py` | `atheriz.objects.base_lock.AccessLock` (mixin, templated) | Permission/lock system (`add_lock`/`access`). Generated via `TemplateGenerator` `new.py:632`. |
| `db_ops.py` | `atheriz.objects.base_db_ops.DbOps` (mixin, copy) | DB serialization (`get_save_ops`/`get_save_ops_clearing`/`get_del_ops`). Copy of `base_db_ops.py` `new.py:626`. |
| `door.py` | `atheriz.objects.base_door.Door` | Represents doors between adjacent nodes. |
| `objects.py` | `atheriz.globals.objects` wrapper | Re-exports `get`/`filter_by`/`get_by_tag` for the game package (`new.py:674`). |
| `database_setup.py` | `atheriz.database_setup` | Creates the SQLite schema (`objects`, `mapdata`, `areas`, `transitions`, `doors`, `gametime`) via `do_setup()` (`new.py:677`). |
| `initial_setup.py` | `atheriz.initial_setup` (patched) | First-start data (superuser creation, world seeding). Patched from `atheriz.initial_setup` `new.py:681`. |
| `connection_screen.py` | `atheriz.connection_screen` (`render`) | Login splash + `get_online()`; imported directly by `atheriz/inputfuncs.py:7` (`new.py:721`). |
| `server_events.py` | `atheriz.server_events` | Hooks `at_server_start/stop/reload` + `at_char_create` (`new.py:726`); imported with fallback `startstop.py:38`. |
| `web/` | `(static assets)` | Webclient templates and static files served by the webserver. |

### 1.3.3 Starting the Server

`atheriz new` automatically starts the server after scaffolding. If you need to start it manually, run the following from inside the game folder:

```sh
atheriz start
```

The server runs in the background by default. Pass `-f` / `--foreground` to attach it to your terminal.

#### Superuser Account

On first creation (`atheriz new my_game`), Atheriz creates a superuser account/character via `initial_setup.do_setup()`. You can pre-set credentials so you are not prompted:

```sh
export ATHERIZ_SUPERUSER_USERNAME=admin
export ATHERIZ_SUPERUSER_PASSWORD=secret
atheriz new my_game
```

If the variables are not set, `atheriz new` prompts interactively during `create_game_folder()` (`atheriz/new.py:570`). `atheriz start` (`atheriz/atheriz.py:436`) does **not** prompt — it calls `do_startup()` → `initial_setup.do_setup()` without interaction; set the env vars before `new` or create the account later with `atheriz create`.

#### CLI Commands

| Command | Description |
|---------|-------------|
| `atheriz new <folder>` | Scaffold a new game folder, then start the server. |
| `atheriz start` | Start the server (background by default; `-f` for foreground). |
| `atheriz stop` | Gracefully stop a running server. |
| `atheriz restart` | Stop, then start the server again. |
| `atheriz reload` | Hot-reload game logic without a full restart. |
| `atheriz reset` | Delete all game data and re-run initial_setup.py. Prompts for confirmation unless `-f` is passed. |
| `atheriz create <account> <character> <password>` | Create an account and character from the command line. Works with a running server (preferred — `/_internal/create_account` via `atheriz/atheriz.py:1136`); falls back to offline `load_objects()` only when no server is detected (`status=="unavailable"`). Accepts `--port`. |
| `atheriz test [core] [pytest_args...]` | Run tests: bare `atheriz test` runs **game tests if inside a game folder**, else core tests; `atheriz test core` forces core (`atheriz/tests`). (`atheriz/atheriz.py:948`, `1329`) |

`start`, `restart`, `new`, `reset` accept **both** `--port` and `--host`; `stop`/`reload` accept `--port` only (`atheriz/atheriz.py:831`, `848`, `865`, `873`). `create --port`, `reset --host/--port` also supported.

### 1.3.4 The Class Injection System
The core mechanic for extending Atheriz is class injection, handled within `settings.py`. By defining `CLASS_INJECTIONS`, you instruct Atheriz to replace its base classes with your game folder's templates. This can be ignored if you're just modifying the default classes in your game folder.

The injection format is a tuple: `(local_module, class_name, target_import_path)`.

```python
# In my_game/settings.py
CLASS_INJECTIONS = [
    ("object", "Object", "atheriz.objects.base_obj"),
]
```
When the engine requests `from atheriz.objects.base_obj import Object`, it receives your custom `Object` class containing your specific rules and overrides. This Python-level monkey-patching applies globally across the server environment.

The generated template ships 9 entries covering `object`, `account`, `channel`, `node`, `door`, `commands.loggedin`, `commands.unloggedin`, `inputfuncs`, `script` (`atheriz/new.py:292`). Each tuple is `(local_module_without_.py, class_name, target_import_path)`; at startup/reload the engine tries `f"{pkg_name}.{local_mod}"` then fallback `local_mod` and does `setattr(target, cls_name, new_cls)` (`atheriz/atheriz.py:157`, `atheriz/reloader.py:201`).

[Table of Contents](./table_of_contents.md) | [Next: 02 Core Concepts](./02_core_concepts.md)
