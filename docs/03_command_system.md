# 03 The Command System

## 3.1 How Commands Work

### 3.1.1 Command Lifecycle
Commands process execution in a sequential flow originating from player WebSocket/Telnet input:

1. The player inputs text; `ConnectionManager` strips escapes and enqueues via `BaseConnection.enqueue_input` (bounded by `CONNECTION_INPUT_QUEUE_LIMIT`, `atheriz/network/connection.py:69`).
2. `dispatch_loggedin(puppet, text, immediate)` (`atheriz/inputfuncs.py:59`) resolves the command: checks `puppet.internal_cmdset`, `LoggedinCmdSet`, location/inventory `external_cmdset`, then `AUTO_COMMAND_ALIASING` (respects `AUTO_ALIAS_IGNORED_KEYS` and `none` fallback, `atheriz/settings.py:192`, `inputfuncs.py:15`).
3. If a match is found and `cmd.access(caller)` passes, `Command.execute(caller, args_string)` parses args.
4. `execute()` (`atheriz/commands/base_cmd.py:135`) does `shlex.split(posix=True)`, handles unbalanced quotes, then `parser.parse_args` under `_parser_lock`; raises `CommandError` for help/usage.
5. `InputFuncs.text()` (`inputfuncs.py:206`) handles `input_future`/`prompt` masking, then calls `dispatch_loggedin(..., immediate=True)` and `atp.run(*job)` (`atp.run(func, caller, args)`) on the async threadpool.

Telnet and WebSocket share this path; `InputFuncs.text()` is the logged-in entry point, `_resolve_unloggedin` handles connection screen.

### 3.1.2 The `Command` Base Class
Custom commands inherit strictly from the parent `Command` class defined in [`atheriz/commands/base_cmd.py`](../atheriz/commands/base_cmd.py). 

Core routing attributes:
- `key`: The absolute keyword matching the command logic.
- `aliases`: An array of alternate trigger words.
- `category`: Used to bucket commands logically within help menu display lists.
- `tag`: Lets you group commands for removing them by tag later.

Primary execution overrides:
- `run()`: The standard entry point containing custom game logic.
- `setup_parser()`: Defines specific command argument constraints.
- `access()`: Verifies execution privileges contextually.
- `print_help()`: Modifies or extends how the command presents system help output.

### 3.1.3 The `GameArgumentParser`
Atheriz wraps `argparse.ArgumentParser` as `GameArgumentParser` (`atheriz/commands/base_cmd.py:19`) to prevent `sys.exit`. It overrides `error()`, `print_help()`, `print_usage()`, and `exit()` all raising `CommandError`; `print_help()` also formats `aliases: …` plus `extra_desc` (`base_cmd.py:117`). Lazy `parser` property (`82`) builds under `_parser_lock` with thread-local guard `_parser_building_local` to avoid recursion.

Argument structures are assembled within `setup_parser()`.
Setting `use_parser = False` completely ignores parsing, yielding the raw `args_string: str` into `run(caller, args)`.

`execute()` splits args via `shlex.split(args_string, posix=True)` (unbalanced quote → `caller.msg("Unbalanced quote…")`), then `parser.parse_args` under lock; `--help` is caught as `CommandError` and shown via `print_help()`.

## 3.2 Creating a Custom Command

### 3.2.1 Step-by-Step: A Simple Command
The `Command` child receives execution data inside `run()`. Ensure the class is appended to the appropriate CmdSet object definition.
Category is used to group commands for the help menu display.

```python
from atheriz.commands.base_cmd import Command

class CmdGreet(Command):
    key = "greet"
    category = "Social"
    use_parser = False

    def run(self, caller, args):
        caller.msg("Hello.")
```

### 3.2.2 Step-by-Step: A Command with Arguments
Defining constraints in `setup_parser` parses arguments strictly prior to invoking `run()`. 

```python
from atheriz.commands.base_cmd import Command

class CmdExamine(Command):
    key = "examine"
    aliases = ["exa"]
    category = "General"
    
    def setup_parser(self):
        self.parser.add_argument("target", help="The object you wish to observe.")
        self.parser.add_argument("--verbose", "-v", action="store_true")
        
    def run(self, caller, args):
        # args is parsed Namespace (or raw str if use_parser=False); no self.args/self.caller
        target_name = args.target
        is_verbose = args.verbose

        caller.msg(f"Examining {target_name}...")
```

### 3.2.3 Access Control on Commands
Access control happens within `access(self, caller)`. Atheriz skips the lock mixin for this class, since most commands will be a custom class anyway. Return `True` to allow execution and `False` to prevent it.

For instance, locking a command specifically for developer ranks:

```python
def access(self, caller):
    return caller.is_builder
```

### 3.2.4 Command Categories and Help
Command configurations influence standard help command displays automatically. Modify `desc`, `extra_desc`, and `category` strings directly. Flagging `hide` suppresses the command entirely from standard help readouts while retaining functionality. `print_help()` utilizes Python's built-in argparse reflection protocols to construct the visual block shown to players using the help command.

## 3.3 Command Sets (`CmdSet`)

### 3.3.1 What is a CmdSet?
A `CmdSet` behaves as a runtime Python dictionary managing `Command` class instantiations, mapping execution calls sequentially against standard identifiers (`key`) and `aliases`.

Two primary sets govern standard game flow:
- `LoggedinCmdSet`: Commands available after logging in.
- `UnloggedinCmdSet`: Commands available before logging in.

These map `key` and `aliases` to `Command` instances under `self.lock` (`atheriz/commands/base_cmdset.py`). Adding a key/alias already registered to a *different* command raises `ValueError: ...already registered... refusing to overwrite...` (`base_cmdset.py:68`); re-registering the same instance is a no-op. Batch `adds()` validates before any insert.

### 3.3.2 Adding Commands to a CmdSet
Commands must instantiate against the `CmdSet` object, commonly during the parent `__init__` sequence.

```python
self.add(CmdExamine())
```
For grouping tags dynamically at startup:
```python
self.adds([cmd1, cmd2], tag="combat_skills")
```
`adds(tag=...)` mutates each `command.tag = tag` (`base_cmdset.py:59`); re-adding a command with a different tag overwrites its previous tag.

### 3.3.3 Dynamic Command Management
CmdSet arrays are modified during runtime via command class calls utilizing `add()`, `remove()`, or filtering target keys referencing `remove_by_tag()`.

Example strategy: A quest script dynamically attaches a temporary search capability tag when accepting an assignment. On completion, the system explicitly calls `.remove_by_tag("quest_14_actions")`, instantly pruning the temporary functionality.

### 3.3.4 Auto Command Aliasing
Toggling `AUTO_COMMAND_ALIASING` (`atheriz/settings.py:192`) supports partial matching, mapping `exa` to `examine` (`atheriz/inputfuncs.py:98`). It respects blocklist `AUTO_ALIAS_IGNORED_KEYS = ["save","quit","wander","exit","logout","disconnect","none"]` (`settings.py:198`, `inputfuncs.py:15`) and short `n/s/e/w/u/d` guard plus single-char `say` shortcut. Unmatched input falls to the `none` command if present. Manage overlapping identifiers with care.

[Table of Contents](./table_of_contents.md) | [Next: 04 Scripts & Hooks](./04_scripts_and_hooks.md)
