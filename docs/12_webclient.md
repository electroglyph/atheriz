# 12 The Webclient

The Atheriz webclient is a powerful, Terminal-based interface designed for deep immersion and ease of use. It handles complex tasks like 24-bit color rendering, map display, and input history management.

## 12.1 Internal "Colon" Commands

The webclient supports several local commands that are handled entirely in the browser (client-side). These commands always start with a colon (`:`).

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `:help` | | Lists all available client-side commands. |
| `:fontsize` | `[size]` | Changes the terminal font size (`6-72`, `webclient/src/webclient/main.ts:458`). Default 19. |
| `:fontfamily` | `[font]` | Changes the terminal font family (joins args, `main.ts:505`). |
| `:contrast` | `[ratio]` | Adjusts the minimum contrast ratio for accessibility (`1-21`, `main.ts:488`). Default 1. |
| `:reader` | | Toggles Screen Reader mode (for NVDA, VoiceOver, etc.). |
| `:glyphs` | | Toggles custom box-drawing glyphs. |
| `:scrollback` | `[rows]` | Sets the number of rows of terminal history to keep (`<number>`, `main.ts:497`). |
| `:record` | | Starts an `asciinema` recording of the session. |
| `:stop` | | Stops the recording and saves a `.cast` file. |
| `:save` | | Saves the current terminal buffer to `history.txt`. |
| `:autosave` | | Toggles automatic saving of history when the connection closes. |
| `:reset` | | Resets all client settings to default and clears local storage. |
| `:draw` | | Opens AtheriZ Draw editor (`main.ts:554` `launchDraw()`). |

## 12.2 WebSocket Protocol (Server-to-Client)

Atheriz uses a structured JSON-over-WebSocket protocol. The following commands can be sent from the server to the client.

### 12.2.1 Core Output
- **`text`**: Standard console output.
  - Arguments: `[message_string]`
- **`prompt`**: Sets or updates the input prompt.
  - Arguments: `[prompt_string]`
- **`buffer`**: Writes a sequence of strings to the terminal with flow control.
  - Arguments: `[array_of_strings]`

### 12.2.2 Multimedia & Accessibility
- **`audio`**: Plays an audio file from the provided URL.
  - Arguments: `[url_string]`
- **`audio_pause`**: Pauses any currently playing audio.
  - Arguments: None
- **`screenreader`**: Informs the client whether screen reader mode should be enabled.
  - Arguments: `[boolean]`

### 12.2.3 Map & Graphics
- **`map_enable` / `map_disable`**: Displays or hides the right-side map pane.
  - Arguments: None
- **`map`**: Full map update.
  - Arguments: `[{map: string, pos: [x,y], symbol: string, legend: Array, area: string, ...}]`
- **`legend`**: Updates the map legend.
  - Arguments: `[{area: string, legend: Array, show_legend: boolean}]`
- **`pos`**: Updates the player's position on the map.
  - Arguments: `[[x, y], symbol (optional)]`
- **`background`**: Sets RGB background highlights for specific coordinates.
  - Arguments: `[{color: [r, g, b], coords: [[x, y], ...]}]`
- **`unbackground`**: Clears all active background highlights.
  - Arguments: None
- **`map_edit_reject`** / **`map_ack`** / **`moves_ok`** / **`moves_denied`**: Draw-editor replies (`atheriz/inputfuncs.py:375`, `webclient/src/webclient/mapedit.ts:342`).
- **`echo_on`** / **`prompt`**: `prompt_masked` flow (`atheriz/objects/session.py:52`, `inputfuncs.py:240`).

### 12.2.4 System Messages
- **`logged_in`**: Notifies the client that the login process is complete. This disables input masking (which prevents password from being echoed).
  - Arguments: None
- **`player_commands`**: populates the client's tab-completion list.
  - Arguments: `[array_of_strings]`
- **`get_map_size`**: Requests the client send back its current map terminal dimensions.
   - Arguments: None
- **`launch_draw`**: Requests that the browser open AtheriZ Draw in a new tab (`webclient/src/webclient/main.ts:397`, `launch.ts:13` may carry `(key,payload)` grant).
   - Arguments: None or `[key, payload]` for Draw grant
   - The client uses the fixed same-origin route `/atheriz_draw/` and shows a link fallback if the browser blocks the popup. `text` always ends with `\r\n` (stripped if `screenreader`, `atheriz/network/connection.py:150`). `buffer` flows via `writeBuffer` (`main.ts:430`).

## 12.3 WebSocket Protocol (Client-to-Server)

The client also sends commands back to the server (validated, queued via `CONNECTION_INPUT_QUEUE_LIMIT` and `STRIP_INPUT_ESCAPE_SEQUENCES`):

- **`text`**: Standard user input.
- **`term_size`** / **`map_size`**: Dimensions (`0 < w <= TERM_SIZE_MAX_WIDTH 1000`, `atheriz/inputfuncs.py:273`, `settings.py:42`).
- **`screenreader`**: Notification that the user toggled screen reader mode.
- **`client_ready`**: Sent when the client initial load is complete.
- **`map_edit`**: `[key, seq, cells]` where cells are `[x,y,symbol]` / `[x,y,char,fg,bg,attrs]` (`fg/bg` `list[int]` or `[-1,-1,-1]`) / `["room",fx,fy,tx,ty]` (`atheriz/inputfuncs.py:337`, validated via `_is_color/_is_attrs`).
- **`map_validate_moves`**: `[key, seq, moves, context]` validated move batch, replies `moves_ok`/`moves_denied` (`inputfuncs.py:424`).

Endpoint is `/ws` (`atheriz/network/websocket.py:158`, `WEBSOCKET_MAX_MESSAGE_SIZE=65536`: 1009 if larger; `max_pending` limits; reconnection `webclient/src/webclient/connection.ts:79`).

## 12.4 AtheriZ Draw

The TypeScript frontend build serves the terminal client at `/webclient/index.html` and the ANSI editor at `/atheriz_draw/`. Build the frontend before starting the server and deploy it into the active game's `web/` directory. The server reports whether the draw entry point is present during startup; it does not build frontend assets at runtime.

[Table of Contents](./table_of_contents.md) | [Next: 13 The Menu Engine](./13_menu_engine.md)
