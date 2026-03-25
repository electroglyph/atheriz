# 12 The Webclient

The Atheriz webclient is a powerful, Terminal-based interface designed for deep immersion and ease of use. It handles complex tasks like 24-bit color rendering, map display, and input history management.

## 12.1 Internal "Colon" Commands

The webclient supports several local commands that are handled entirely in the browser (client-side). These commands always start with a colon (`:`).

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `:help` | | Lists all available client-side commands. |
| `:fontsize` | `[size]` | Changes the terminal font size. Default is 19. |
| `:fontfamily` | `[font]` | Changes the terminal font family (e.g., `"Fira Custom"`). |
| `:contrast` | `[ratio]` | Adjusts the minimum contrast ratio for accessibility. Default is 1. |
| `:reader` | | Toggles Screen Reader mode (for NVDA, VoiceOver, etc.). |
| `:glyphs` | | Toggles custom box-drawing glyphs. |
| `:scrollback` | `[rows]` | Sets the number of rows of terminal history to keep. |
| `:record` | | Starts an `asciinema` recording of the session. |
| `:stop` | | Stops the recording and saves a `.cast` file. |
| `:save` | | Saves the current terminal buffer to `history.txt`. |
| `:autosave` | | Toggles automatic saving of history when the connection closes. |
| `:reset` | | Resets all client settings to default and clears local storage. |

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

### 12.2.4 System Messages
- **`logged_in`**: Notifies the client that the login process is complete. This disables input masking (which prevents password from being echoed).
  - Arguments: None
- **`player_commands`**: populates the client's tab-completion list.
  - Arguments: `[array_of_strings]`
- **`get_map_size`**: Requests the client send back its current map terminal dimensions.
  - Arguments: None

## 12.3 WebSocket Protocol (Client-to-Server)

The client also sends commands back to the server:

- **`text`**: Standard user input.
- **`term_size`**: Updated dimensions of the main terminal.
- **`map_size`**: Updated dimensions of the map pane.
- **`screenreader`**: Notification that the user toggled screen reader mode.
- **`client_ready`**: Sent when the client initial load is complete.

[Table of Contents](./table_of_contents.md) | [Next: 13 API Reference](./13_api_reference.md)
