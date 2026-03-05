# 08 Input Handling & the WebSocket Layer

## 8.1 The WebSocket Connection

### 8.1.1 Connection Lifecycle
Atheriz routes basic connections handling standard WebSocket protocols intrinsically. 
1. Client connects externally.
2. A generic `Connection` wrapper object initializes tracking localized connection parameters internally.
3. Upon finalizing the handshake, Atheriz dispatches `client_ready`, transmitting base configuration options directly toward the renderer interface rendering the main screen logic reliably.

Reference `atheriz/websocket.py` tracing structural API mechanics defining the wrapper implementation reliably.

### 8.1.2 Message Format
Communications utilize a structured JSON format universally passing between the primary client UI and the engine parsing interface logic.

`[command_name, [positional_args], {kwargs}]`

Built-in native commands encompass: `text`, `term_size`, `map_size`, `screenreader`, and `client_ready`. Expanding the system allows inserting custom rendering structures securely natively parsed against custom interface configurations directly mapping variables inside the `webclient.js` source code securely.

## 8.2 Input Functions

### 8.2.1 The `InputFuncs` Class
The `InputFuncs` module delegates the mapping linking designated strings extracted against custom functions executed across identical names directly. The system identifies targets actively through an implicit `@inputfunc` execution wrapper assigning functions logically upon startup.

Reference `atheriz/inputfuncs.py` examining the complete logic block defining automated registration procedures executed natively through `get_handlers()`.

### 8.2.2 The `text` Handler
Player actions resolve inherently via `text()`. Flow logic defines the execution string uniformly:
1. Strips unformatted whitespace natively.
2. Identifies matching CmdSet strings resolving dynamically referencing object command constraints simultaneously.
3. Invokes validation tests initiating `command.execute()`.
4. Completes logic calling `command.run()`.

Inspecting `InputFuncs.text()` reveals the precise insertion point where external pre-processing logic (profanity filtration or comprehensive logging sequences) must reside securely resolving before command completion processing completes successfully.

### 8.2.3 Creating Custom Input Handlers
Modifying connection constraints requires directly extending `InputFuncs`. Create new target wrappers assigning strings exactly against decorators mapping targeted structures identically.

```python
from atheriz.inputfuncs import InputFuncs, inputfunc

class GameInputFuncs(InputFuncs):
    @inputfunc("minimap_click")
    def handle_map_click(self, connection, *args, **kwargs):
        x, y = args[0]
        # Resolve pathfinding against coordinates precisely here.
```

Register the file configuration safely against the `settings.py` `CLASS_INJECTIONS` list explicitly redefining target overrides logically processing the incoming application payload actively mapping strings identically across targets.

[Table of Contents](./table_of_contents.md) | [Next: 09 Time System](./09_time_system.md)
