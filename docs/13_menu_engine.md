# 13 The Menu Engine

Atheriz provides a simple, stateful `MenuEngine` for creating interactive, multi-step menus.

## 13.1 Core Components

1. **`MenuContext`**: Passed to every menu node. Holds `caller` (the player) and a `state` dictionary where you can store data between steps.
2. **`Choice`**: A single option the player can type. `Choice(key, desc, goto=None, callback=None, stay=False)` — `key` is what the player types, `desc` is what the menu shows, `goto` moves to another node, `callback` runs code when the choice is picked, and `stay=True` keeps the player on the same node.
3. **`MenuNode`**: A function that takes a `MenuContext` and returns the text to show and a list of `Choice` objects: `return text, [Choice(...), ...]`. You can write nodes and callbacks as regular `def` functions, or as `async def` if they need to wait for something.

## 13.2 Basic Example

```python
from atheriz.menu import Choice, MenuContext, run_menu

def node_start(ctx: MenuContext):
    return "Welcome! Would you like to create a new character?", [
        Choice(key="Y", desc="Yes, let's start", goto=node_create),
        Choice(key="N", desc="No, quit", goto=None)
    ]

def node_create(ctx: MenuContext):
    ctx.state["creating"] = True
    return "Great! Creating character...", [
        Choice(key="C", desc="Continue", goto=None)
    ]

run_menu(caller, node_start)
```

`run_menu` starts the menu and returns right away — your command does not need to wait for the player to finish. If you need to do async work inside a node or callback, just use `async def`:

```python
async def node_async(ctx: MenuContext):
    data = await fetch_something(ctx.caller)
    return f"Found {data}", [Choice(key="Q", desc="Quit", goto=None)]

async def on_pick(ctx: MenuContext):
    await save_choice(ctx.state)

def node_with_async_callback(ctx: MenuContext):
    return "Pick one", [Choice(key="1", desc="Save", callback=on_pick, goto=None)]
```

## 13.3 Handling Input

- **Case insensitive**: Input is lowercased and stripped, so `y`, `Y`, and `  y  ` all match `Choice(key="Y")`.
- **Invalid choices**: If the player types something that does not match any `key`, the menu is shown again.
- **Timeout and disconnect**: Each prompt waits up to 60 seconds. If the player does not answer or disconnects, the menu closes automatically.

## 13.4 Callbacks and Staying on the Current Node

A `callback` lets you run code when a choice is picked. Often you want to update state and show the same menu again so the player can see the change. Use `stay=True` for that.

```python
def settings_node(ctx: MenuContext):
    if "verbose" not in ctx.state:
        ctx.state["verbose"] = False

    def toggle_verbose(ctx_inner: MenuContext):
        ctx_inner.state["verbose"] = not ctx_inner.state["verbose"]

    current = "ON" if ctx.state["verbose"] else "OFF"
    text = f"--- Settings ---\nVerbose mode is currently: {current}\nChoose an option:"

    return text, [
        Choice(key="1", desc="Toggle Verbose Mode", callback=toggle_verbose, stay=True),
        Choice(key="Q", desc="Quit Menu", goto=None)
    ]
```

When the player types `1`, `toggle_verbose` runs and the same node is shown again with the updated text. If a choice has a `callback` but no `goto` and no `stay=True`, the menu exits after the callback runs.

## 13.5 MenuEngine API

- `MenuEngine(caller, start_node)` — create a menu starting at `start_node`.
- `get_display() -> str` — text for the current node, formatted as `  [key] desc` lines.
- `handle_input(text) -> bool` — handle one line of player input. Returns `True` to keep showing the menu, `False` when the menu is done.
- `close()` — stop the menu and clear its state.
- `run_menu(caller, start_node)` — start a menu for a player. Handles prompting, input, timeouts, and cleanup for you.

[Table of Contents](./table_of_contents.md) | [Next: 14 API Reference](./14_api_reference.md)
