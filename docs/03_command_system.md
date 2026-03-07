# 03 The Command System

## 3.1 How Commands Work

### 3.1.1 Command Lifecycle
Commands process execution in a sequential flow originating from player WebSocket input:

1. The player inputs text strings.
2. The payload is grabbed by `InputFuncs.text()`.
3. The parser isolates the target identifier and queries the current `CmdSet`.
4. If a match is found, the system requests `Command.execute()`.
5. Configuration permitting, execution resolves entirely through `Command.run()`.

For exact control trace code, observe `InputFuncs.text()` inside [`atheriz/inputfuncs.py`](../atheriz/inputfuncs.py).

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
Atheriz wraps standard Python argument execution (`argparse.ArgumentParser`) to prevent system crashes triggered by standard `sys.exit()` command-line failures. This is mostly argparse, just patched a bit to not exit the process, heh.

Argument structures are assembled within `setup_parser()`.
Setting `use_parser = False` in the class definition completely ignores parsing, yielding the raw unformatted string into `run()`.

Argument splits handles quoted structures automatically using Python's `shlex.split`. A phrase like `give "iron sword" to Bob` properly registers the string block.

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
    
    def run(self):
        self.caller.msg("Hello.")
```

### 3.2.2 Step-by-Step: A Command with Arguments
Defining constraints in `setup_parser` parses arguments strictly prior to invoking `run()`. 

```python
from atheriz.commands.base_cmd import Command

class CmdExamine(Command):
    key = "examine"
    aliases = ["exa"]
    category = "Observation"
    
    def setup_parser(self):
        self.parser.add_argument("target", help="The object you wish to observe.")
        self.parser.add_argument("--verbose", "-v", action="store_true")
        
    def run(self, caller: Object, args):
        # Access variables via self.args
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

These are simple dictionaries without any logic for merging. If you add a command with the same key as an existing command, it will overwrite the existing command. Review `atheriz/commands/base_cmdset.py` for deeper context.

### 3.3.2 Adding Commands to a CmdSet
Commands must instantiate against the `CmdSet` object, commonly during the parent `__init__` sequence.

```python
self.add(CmdExamine())
```
For grouping tags dynamically at startup:
```python
self.adds([cmd1, cmd2], tag="combat_skills")
```

### 3.3.3 Dynamic Command Management
CmdSet arrays are modified during runtime via command class calls utilizing `add()`, `remove()`, or filtering target keys referencing `remove_by_tag()`.

Example strategy: A quest script dynamically attaches a temporary search capability tag when accepting an assignment. On completion, the system explicitly calls `.remove_by_tag("quest_14_actions")`, instantly pruning the temporary functionality.

### 3.3.4 Auto Command Aliasing
Toggling `AUTO_COMMAND_ALIASING` configuration supports partial matching, mapping inputs like `exa` to `examine`. Naming collision occurs frequently utilizing this setting; manage overlapping identifiers with care.

[Table of Contents](./table_of_contents.md) | [Next: 04 Scripts & Hooks](./04_scripts_and_hooks.md)
