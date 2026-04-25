# 15. Sound Propagation

Atheriz features a robust acoustic system that handles how sounds are emitted, attenuated over distance, and intercepted by objects and rooms. This system allows for realistic audio propagation across the game map, taking into account open pathways and closed doors.

## Emitting Sounds

To emit a sound from an object, use the `emit_sound` method.

```python
def emit_sound(self, sound_desc: str, sound_msg: str, loudness: float, is_say: bool = False):
```

- `sound_desc`: The descriptive part of the sound (e.g., "A loud bang", "Someone says,").
- `sound_msg`: The actual message or quote (e.g., " 'Hello there!'", "").
- `loudness`: The intensity of the sound in decibels (e.g., `100.0` for a loud bang, `60.0` for normal speech).
- `is_say`: A boolean indicating if the sound is spoken dialogue.

### Example: Emitting a Sound

```python
emitter = Object.create(None, "A strange machine")
emitter.emit_sound("A strange machine whirs loudly", " *CLANK*", loudness=100.0, is_say=False)
```

## Propagation and Attenuation

When a sound is emitted, it follows this lifecycle:

1. **Local Room:** The sound is first heard by all objects in the same room as the emitter.
2. **Breadth-First Search (BFS):** If the emitter is inside a node (room) on the map, the sound begins to propagate to neighboring nodes using a BFS algorithm.
3. **Attenuation:** As the sound travels from one node to the next, its `loudness` decreases (attenuates).
   - If the pathway is open (e.g., no doors, or open doors), `settings.DEFAULT_OPEN_SOUND_ATTENUATION` (default 10.0 dB) is subtracted.
   - If the pathway is closed or enclosed, `settings.DEFAULT_ENCLOSED_SOUND_ATTENUATION` (default 20.0 dB) is subtracted.
4. **Termination:** The sound stops propagating along a path once its `loudness` reaches 0 or below.

## Hearing Sounds

Objects process incoming sounds through the `at_hear` hook.

```python
@hookable
def at_hear(self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool):
```

In the base implementation (`base_obj.py`), `at_hear` uses the sound's remaining `loudness` to categorize it using `settings.LOUDNESS_LEVELS` (e.g., "faint", "clear", "nearly inaudible"). It also calculates the relative direction from the listener to the emitter if the sound originated in a different room.

### Example: Default Hearing Behavior

In `base_obj.py`, the default `at_hear` implementation processes the sound's loudness, determines the direction of the sound if it came from another room, applies word replacement for faint speech, and formats the final message with ANSI colors before sending it to the player:

```python
    @hookable
    def at_hear(self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool):
        # ... (initial checks omitted) ...
        
        adj = next((desc for threshold, desc in LOUDNESS_LEVELS if loudness < threshold), "deafening")

        if is_say and sound_msg:
            replace_pct = next((pct for threshold, pct in settings.REPLACE_LEVELS if loudness < threshold), 0)
            if replace_pct > 0:
                sound_msg = word_replace(sound_msg, replace_pct / 100.0)

        emitter_loc = emitter.location
        if emitter_loc == loc or not emitter_loc:
            self.msg(f"{wrap_xterm256(f'You hear something{adj}:', fg=15, bold=True)} {sound_desc}{sound_msg}")
        else:
            direction = get_dir(loc.coord, emitter_loc.coord)
            z_diff = emitter_loc.coord[3] - loc.coord[3]
            z_str = "" if z_diff == 0 else ("from above you " if z_diff > 0 else "from below you ")
            self.msg(
                f"{wrap_xterm256(f'You hear something{adj} {z_str}to the {direction}:', fg=15, bold=True)} {sound_desc}{sound_msg}"
            )
```

### Pre-Hear and Pre-Emit Hooks

- `at_pre_emit_sound(self, emitter, sound_desc, sound_msg, loudness, is_say)`: Called before a sound is actually emitted. Returning `False` as the first element of the returned tuple will cancel the emission.
- `at_pre_hear(self, emitter, sound_desc, sound_msg, loudness, is_say)`: Called before an object or node processes a received sound. Returning `False` will cause the listener to ignore the sound.

## Muffling Speech (`is_say=True`)

When `is_say` is `True`, Atheriz applies an additional layer of realism. Based on the `loudness` of the sound when it reaches the listener, words in `sound_msg` may be replaced with `"..."`.

This is governed by `settings.REPLACE_LEVELS`:

```python
# settings.py
# (decibels, percentage of words to replace)
REPLACE_LEVELS = (
    (1, 95.0),
    (10, 80.0),
    (20, 60.0),
    (30, 40.0),
    (40, 20.0),
    (50, 10.0),
)
```

If a "say" message is very faint when it arrives (e.g., loudness = 15 dB), there's a 60% chance for each word to be obscured, simulating the difficulty of hearing distant or quiet conversations.

```python
# The original sound: "I am hiding the treasure in the cave."
# What the listener might hear from 3 rooms away:
"You hear something faint to the north: Someone says, 'I am ... the ... in ... cave.'"
```

[Previous: 14 API Reference](./14_api_reference.md) | [Table of Contents](./table_of_contents.md)
