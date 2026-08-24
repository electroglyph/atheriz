# 15 Sound Propagation

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

When a sound is emitted via `obj.emit_sound(sound_desc, sound_msg, loudness, is_say=False)` (queued as `atp.add_task(at_emit_sound)` `atheriz/objects/base_obj.py:1778`, dropped with warning if queue full):

1. **Local Room:** The sound is first heard by all objects in the same room as the emitter (`msg_contents` path).
2. **Breadth-First Search (BFS):** If the emitter is inside a node on the map, sound propagates only **within the same `NodeArea`** via `area.get_neighbors()` (`atheriz/objects/base_obj.py:1734`, `atheriz/objects/nodes.py:1281`), including vertical `(0,0,±1)` but ignoring cross-area `Transition` links.
3. **Attenuation:** As the sound travels, `loudness` decreases:
   - Per-node override: each `Node` has `open_attenuation`/`enclosed_attenuation`/`ambient_sound_level` defaulting to `settings.DEFAULT_OPEN_SOUND_ATTENUATION` `10.0` / `DEFAULT_ENCLOSED_SOUND_ATTENUATION` `20.0` / `DEFAULT_AMBIENT_SOUND_LEVEL` `5.0` (`atheriz/objects/nodes.py:133`, `settings.py:91`; rooms can override). If listener's `ambient_sound_level` exceeds incoming `loudness`, delivery is suppressed (`nodes.py:318`).
   - Otherwise `settings.DEFAULT_*` subtracted (`base_obj.py:1706`).
4. **Termination:** Propagation continues only while returned loudness `>0` (`base_obj.py:1770`); `Node.at_hear` returns `float` remaining loudness and `Object.at_hear` via BFS controls queue (`nodes.py:292`).

## Hearing Sounds

Objects process incoming sounds through the `at_hear` hook.

```python
@hookable
def at_hear(self, emitter: Object, sound_desc: str, sound_msg: str, loudness: float, is_say: bool):
```

In the base implementation (`atheriz/objects/base_obj.py:1668`), `at_hear` uses `LOUDNESS_LEVELS` thresholds (`atheriz/settings.py:296`: `(20," nearly inaudible")` etc; `60→""` no adjective — "clear" is empty) to pick `adj`, and only sends the directioned message when `emitter_loc.coord.area == loc.coord.area` (otherwise no message).

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
        elif emitter_loc.coord.area == loc.coord.area:
            direction = get_dir(loc.coord, emitter_loc.coord)
            z_diff = emitter_loc.coord.z - loc.coord.z
            z_str = "" if z_diff == 0 else (" from above you" if z_diff > 0 else " from below you")
            dir_str = f" to the {direction}" if direction else ""
            self.msg(
                f"{wrap_xterm256(f'You hear something{adj}{z_str}{dir_str}:', fg=15, bold=True)} {sound_desc}{sound_msg}"
            )
        # no message if different area (BFS is area-bounded)
```

### Pre-Hear and Pre-Emit Hooks

- `at_pre_emit_sound(self, emitter, sound_desc, sound_msg, loudness, is_say)`: Called before a sound is actually emitted. Returning `False` as the first element of the returned tuple will cancel the emission.
- `at_pre_hear(self, emitter, sound_desc, sound_msg, loudness, is_say)`: Called before an object (`atheriz/objects/base_obj.py:1727` — `if not allow: continue` skips that listener, propagation continues) or node (`atheriz/objects/nodes.py:285` — `if not allow or loudness <= ambient: return loudness-attenuation`, still propagates attenuated sound; to stop transmission reduce returned loudness). Node returns `float`, Object path skips individual listener.

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
