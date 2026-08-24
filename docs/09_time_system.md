# 09 The Time System

## 9.1 How Time Works

### 9.1.1 The Game Clock
Atheriz separates internal game time from server uptime. Every `TIME_UPDATE_SECONDS` real seconds (default `1.0`, `atheriz/settings.py:245`) the clock advances by `TICK_MINUTES` game minutes (default `1.0`, `settings.py:249`) via `GameTime.on_tick` (`atheriz/globals/time.py:192`, gated by `TIME_SYSTEM_ENABLED=True` `settings.py:233`). 1 real hour = 60 game hours (2.5 days) at defaults. Calendar mapping (`START_YEAR=888` etc, days/month) is in `atheriz/globals/time.py`. `get_time()` returns `year, month, day, hour, minute, second, moon_phase, formatted, season, …`.

## 9.2 Solar & Lunar Events

### 9.2.1 Sunrise & Sunset
When the game clock reaches `SUNRISE_HOUR` or `SUNSET_HOUR`, the global clock loops through eligible game objects and triggers the `at_solar_event(msg)` hook on them.

Objects receive this hook if they match the `SOLAR_RECEIVER_LAMBDA` filter defined in your `settings.py`. By default, only connected players receive sunrise/sunset messages:
```python
SOLAR_RECEIVER_LAMBDA = lambda x: x.is_pc and x.is_connected
```
If you wanted NPCs to also react to sunrise/sunset, you could override this variable in your game folder's `settings.py`:
```python
SOLAR_RECEIVER_LAMBDA = lambda x: (x.is_pc and x.is_connected) or x.is_npc
```

### 9.2.2 Moon Phases
`LUNAR_CYCLE_DAYS` controls the duration of the lunar cycle (default 30 days). When a phase shifts, the `at_lunar_event(msg)` hook triggers on objects passing the `LUNAR_RECEIVER_LAMBDA` filter setup.

The current moon phases calculated natively are: "new", "waxing crescent", "first quarter", "waxing gibbous", "full", "waning gibbous", "third quarter", and "waning crescent".

## 9.3 Ticks & Alarms

### 9.3.1 The Tick System
Per-object ticks are not polled on global `ticks`; each `is_tickable` object/node registers `obj.at_tick` as a coro on `AsyncTicker.TimeSlot(interval=tick_seconds)` (`atheriz/globals/asyncthreadpool.py:385`, `atheriz/objects/base_obj.py:529`). `time.py:178` `add_coro(on_tick, TIME_UPDATE_SECONDS)` drives the game clock independently of object ticks.

Prefer `Object.create(caller, name, is_tickable=True, tick_seconds=5)` (`base_obj.py:118`) which atomically registers; manual `self.is_tickable=True; self.tick_seconds=5` works via remove/add but `Node` defaults `Flags` `False` (`atheriz/objects/nodes.py:217`). `tick_seconds`/`is_tickable` setters auto add/remove the ticker (`base_obj.py:517-541`, `nodes.py:217-229`).

### 9.3.2 Alarms
`GameTime.add_alarm(hour, minute, caller, repeat=False, data=None)` (`atheriz/globals/time.py:107`; `hour/minute` coerced to `str`, `data` must be `dict|None` else `TypeError` `124`) schedules `caller.at_alarm(time, data)` (`atheriz/objects/base_obj.py:586`) when `after_time` matches. Remove via `remove_alarm`/`remove_alarms_by_caller`.

Wildcards: `("?", minute)` fires every hour at that minute, `(hour, "?")` fires every minute of that hour (`time.py:199`); `("?","?")` not supported. Queue-full `add_task` may retry/inline (`time.py:228`).

Example: shop at `08:00` (`add_alarm("8","0", shop, repeat=True)`), lock doors at midnight.

[Table of Contents](./table_of_contents.md) | [Next: 10 Utilities & Advanced Topics](./10_utilities_advanced.md)
