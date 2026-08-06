# 08 Input Handling & the WebSocket Layer

## 8.1 The WebSocket Connection

### 8.1.1 Connection Lifecycle
Atheriz uses FastAPI to handle WebSocket connections. 
1. When a client connects, Atheriz accepts the connection and creates a `Connection` wrapper object to manage it.
2. The client handshake finishes and typically sends a `client_ready` message.
3. The server responds to `client_ready` by rendering the welcome screen and prompting for login.

Reference `atheriz/network/websocket.py` and `atheriz/network/connection.py` for the core implementation of the `WebSocketProtocol`/`Connection` classes.

### 8.1.2 Message Format
Communications between the client UI and the game server use a structured JSON format. Every message sent to the server must be a list with three elements:

`[command_name, [positional_args], {kwargs}]`

Built-in message commands natively handled by the engine include: `text`, `term_size`, `map_size`, `screenreader`, and `client_ready`. You can add custom commands (like button clicks or UI events) by writing custom input handlers on the server and sending matching JSON arrays from the client.

### 8.1.3 Login Flow
The connection screen is rendered by `atheriz/connection_screen.py`. When `ACCOUNT_CREATION_ENABLED` is `True`, it shows an `enter 'create' to make a new account` hint. The unlogged-in command set (`atheriz/commands/unloggedin/`) handles the flow:

1. `connect` logs an existing account in; after a successful login the player is routed through character selection (`char_selection` in `connect.py`), which lists their characters and lets them pick one (or `new`).
2. `create` (key `create`, available when `ACCOUNT_CREATION_ENABLED` is `True`) prompts for a name and password, creates a new account, auto-logs the player in, and routes them straight to character selection.
3. `new` (key `new`, available when `CHAR_CREATION_ENABLED` is `True`) lets a logged-in account create a new character — name, gender, and description prompts, mirroring the guest flow — and attaches the new `is_pc` object to the account.
4. `guest` (available when `GUEST_ENABLED` is `True`) connects without an account.

## 8.2 Input Functions

### 8.2.1 The `InputFuncs` Class
The `InputFuncs` class maps incoming JSON message commands (like `"text"` or `"map_size"`) to python methods. It does this automatically by scanning for methods decorated with `@inputfunc()`.

Reference `atheriz/inputfuncs.py` for the base implementations.

### 8.2.2 The `text` Handler
Standard player commands (like typing "look" or "say hello") are sent as `text` messages. The `text` handler does the following:
1. Receives the raw string from the client.
2. Checks if the player is in a prompt/input state (resolving `input_future` if so).
3. Splits the text to find the command name and its arguments.
4. Searches for the command in the appropriate command sets (unlogged-in, logged-in, objects in room, inventory, etc.).
5. If a command is found, it schedules it for execution in the async threadpool.

### 8.2.3 Creating Custom Input Handlers
To add new WebSocket message handlers or override existing ones, extend the base `InputFuncs` class and use the `@inputfunc` decorator.

For example, to handle a custom `"ping"` message from your web client:

```python
from atheriz.inputfuncs import InputFuncs as BaseInputFuncs, inputfunc

class InputFuncs(BaseInputFuncs):
    
    @inputfunc("ping")
    def handle_ping(self, connection, args, kwargs):
        # Replies back to the client
        connection.msg("pong!")
```

If you do not pass a string name to `@inputfunc()`, it defaults to using the name of the function.

To ensure your game uses this custom class instead of the default one, add it to `CLASS_INJECTIONS` inside your `settings.py` so the core engine swaps it out on startup:
```python
CLASS_INJECTIONS = [
    ("inputfuncs", "InputFuncs", "atheriz.inputfuncs"),
]
```

[Table of Contents](./table_of_contents.md) | [Next: 09 Time System](./09_time_system.md)
