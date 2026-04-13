# 13 The Menu Engine

Atheriz provides a simple, stateful `MenuEngine` for creating interactive, multi-step menus. The engine is designed to handle user inputs asynchronously in the background to avoid blocking the main server loop.

## 13.1 Core Components

The menu system relies on three primary components:

1. **`MenuContext`**: An object passed between menu nodes that holds a reference to the `caller` (the user interacting with the menu) and a `state` dictionary for persisting data between steps.
2. **`Choice`**: A dataclass representing an available option in a menu. Choices define what the user types (`key`), what the menu displays (`desc`), and whether the choice shifts the menu to a new node (`goto`) or executes a side effect (`callback`).
3. **`MenuNode`**: A callable (a function) that takes the `MenuContext` and returns a tuple containing the display string and a list of `Choice` objects: `(text, choices_list)`.

## 13.2 Basic Example

Here is an example of a simple two-step menu:

```python
from atheriz.menu import Choice, MenuContext, run_menu

def node_start(ctx: MenuContext):
    return "Welcome to the game! Would you like to create a new character?", [
        Choice(key="Y", desc="Yes, let's start", goto=node_create),
        Choice(key="N", desc="No, quit", goto=None)
    ]

def node_create(ctx: MenuContext):
    # We can save variables to the ctx.state dict
    ctx.state["creating"] = True
    return "Great! Creating character...", [
        Choice(key="C", desc="Continue", goto=None)
    ]

# To start the menu for a player:
# run_menu(caller, node_start)
```

## 13.3 Handling Input

- **Case Insensitive**: Menu inputs are lowercased and whitespace-stripped. A user can type `y`, `Y`, or `y` and it will correctly trigger the `Choice(key="Y")`.
- **Invalid Choices**: If the player enters a string that doesn't match any choice `key`, the engine will simply redisplay the current menu context to prompt them again.

## 13.4 Callbacks and Staying on the Current Node

Choices can take an optional `callback` function, which is useful for executing side effects when a user selects an option.

Often, you want a choice to simply update some state and then **refresh the current menu** so the user can see their changes and continue making selections. To accomplish this cleanly, you can use the `stay=True` argument.

Here is a realistic example of a Settings Menu. We want the user to be able to toggle "Verbose Mode" on and off, see the menu text update to reflect their choice, and stay in the menu until they explicitly decide to quit.

```python
def settings_node(ctx: MenuContext):
    # 1. Initialize state if it hasn't been set yet
    if "verbose" not in ctx.state:
        ctx.state["verbose"] = False

    # 2. Define our callback that mutates the state
    def toggle_verbose(ctx_inner: MenuContext):
        ctx_inner.state["verbose"] = not ctx_inner.state["verbose"]

    # 3. Dynamically generate the menu string based on the current state
    current_status = "ON" if ctx.state["verbose"] else "OFF"
    text = f"--- Settings ---\nVerbose mode is currently: {current_status}\nChoose an option:"

    # 4. Return the text and choices
    return text, [
        Choice(
            key="1",
            desc="Toggle Verbose Mode",
            callback=toggle_verbose,
            stay=True # Automatically re-renders this node after the callback
        ),
        Choice(key="Q", desc="Quit Menu", goto=None)
    ]
```

**What this accomplishes:**
When the user types `1`, the engine executes `toggle_verbose`. Then, because `stay=True`, the engine automatically re-runs the current node function. The node reconstructs the text (`Verbose mode is currently: ON`) and reprompts the user with the updated display.

If a choice has a callback but _omits_ both `goto` and `stay=True`, the engine defaults to executing the callback and immediately **exiting the menu entirely**.
[Table of Contents](./table_of_contents.md) | [Next: 14 API Reference](./14_api_reference.md)
