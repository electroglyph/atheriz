# 08 Input Handling & the WebSocket Layer

## 8.1 The WebSocket Connection

### 8.1.1 Connection Lifecycle
Atheriz uses FastAPI at `GET /ws` (`atheriz/network/websocket.py:158`, `WEBSOCKET_MAX_MESSAGE_SIZE=65536`: close 1009 if larger, pending-send limits `WEBSOCKET_MAX_PENDING_SENDS/BYTES`). On connect it checks `is_ip_banned` and `MAX_CONNECTIONS_PER_IP` (`atheriz/network/manager.py:68`), registers via `ConnectionManager`, and creates `WebSocketConnection`/`TelnetConnection`. Telnet auto-dispatches `client_ready` (`atheriz/network/telnet.py:356`, `TELNET_MAX_LINE`, NAWS clamp) and negotiates `telnet_tls`.
Reference `atheriz/network/websocket.py`, `atheriz/network/connection.py`, and `atheriz/network/manager.py`.

### 8.1.2 Message Format
Communications between the client UI and the game server use a structured JSON format. Messages are lists ` [command_name, [positional_args], {kwargs}]` (`atheriz/network/manager.py:168`), but the server is lenient: 1 element (`[cmd]`) is accepted, missing `args` defaults to `[]`, missing `kwargs` to `{}`; `STRIP_INPUT_ESCAPE_SEQUENCES` (`atheriz/settings.py:40`) strips CSI/OSC/null (`manager.py:199`) and throttles malformed input (`manager.py:10`, `_MALFORMED_WINDOW=5.0`).

Built-in message commands natively handled by the engine include: `text`, `term_size`, `map_size`, `screenreader`, `client_ready`, plus `map_edit` and `map_validate_moves` for AtheriZ Draw (authenticated via rotating `mapedit` key chain, `atheriz/inputfuncs.py:337`). Unknown commands only `logger.debug`. Add custom commands by writing input handlers and sending matching JSON arrays from the client.

### 8.1.3 Login Flow
The connection screen is rendered by `atheriz/connection_screen.py` (`render(session)` + `get_online()`). When `ACCOUNT_CREATION_ENABLED` is `True`, it shows `enter 'create' to make a new account`. The unlogged-in command set (`atheriz/commands/unloggedin/cmdset.py:13` — always includes `GuestCommand`; `CreateCommand`/`NewCharacterCommand` conditional) handles:

1. `connect` (`connect.py:15` `char_selection`, `75` `ConnectCommand`): shows `[banned]` tag, checks `at_pre_puppet`, puppet guard (`session`, `is_deleted`), increments `failed_login_attempts`, bans IP via `ban_ip` after `>MAX_LOGIN_ATTEMPTS` (`LOGIN_ATTEMPT_COOLDOWN`), checks `account.is_banned` → close, sends `logged_in`.
2. `create` / `new` / `guest` enforce unified `CREATION_COOLDOWN` via `try_reserve_creation_cooldown`/`apply_creation_cooldown` (`guest.py:52`, `create.py:31`, `new.py:41`), validate via `validation.py` (`MAX_ACCOUNT_NAME_LENGTH` etc), `new` checks `MAX_CHARACTERS`, `guest` sets `is_temporary=True` (`guest.py:90`, `save_objects` skips). Route through `char_selection` (or `new`) and auto-login.

## 8.2 Input Functions

### 8.2.1 The `InputFuncs` Class
The `InputFuncs` class maps incoming JSON message commands (like `"text"` or `"map_size"`) to python methods. It does this automatically by scanning for methods decorated with `@inputfunc()`.

Reference `atheriz/inputfuncs.py` for the base implementations.

### 8.2.2 The `text` Handler
Standard player commands (`look`, `say hello`) are sent as `text` messages (`atheriz/inputfuncs.py:206-266`, enqueued via `BaseConnection.enqueue_input` `CONNECTION_INPUT_QUEUE_LIMIT` FIFO, `busy` throttle `connection.py:69`). `text()` atomically checks `session.lock` `input_future` (`223`), handles `_input_masked`/`echo_on`/`prompt_masked` (`session.py:99`), `call_soon_threadsafe(future.set_result)` if in prompt else snapshots `puppet` (`251`), calls `dispatch_loggedin(..., immediate=True)` (`59`, resolves `puppet.internal_cmdset` → `LoggedinCmdSet` → `external_cmdset` → `AUTO_COMMAND_ALIASING` with `_IGNORE_KEYS`/`_NO_ALIAS_COMMANDS:16` → `none` fallback → `access` → `execute`) and schedules `atp.run(*job)` on the threadpool. `BaseConnection.msg` appends `\r\n` and strips ANSI if `screenreader` (`connection.py:150`).

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
