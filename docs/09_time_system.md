# 09 The Time System

## 9.1 How Time Works

### 9.1.1 The Game Clock
Atheriz separates internal game time from server uptime. Every N real-world seconds (defined by `TIME_UPDATE_SECONDS` in `settings`), the game clock advances by N in-game minutes (defined by `TICK_MINUTES`). 

These settings natively default to 1 real second advancing 1 game minute, which means 1 real hour represents 60 game hours (2.5 game days). The calendar mapping logic (days per month, months per year, hours per day) is managed in `atheriz/globals/time.py`.

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
The `TIME_UPDATE_SECONDS` frequency dictates the tick resolution of the system. Atheriz uses a background async ticker loop to drive real-time engine operations natively. While time calculations drive hooks based on in-game hours, ticks act locally on objects. 

Any game object (including rooms/nodes) with an active `is_tickable` property checks an internal `tick_seconds` reference logic. When elapsed ticks match the expected duration, the object safely triggers its custom `at_tick()` loop hook asynchronously.

To create an NPC that executes an action every 5 seconds, simply enable `self.is_tickable = True` inside their init, assign `self.tick_seconds = 5`, and write an `at_tick(self)` routine defining exactly what must occur.

### 9.3.2 Alarms
The `at_alarm(time, data)` hook schedules callbacks targeting specific synchronized in-game times globally tracked by `GameTime`.

Using `GameTime.add_alarm(hour, minute, caller_obj, repeat=False, data=None)`, you can queue logic to fire precisely when the clock aligns with the assigned tuple. This is incredibly useful for scheduling routines like opening shops at 08:00 AM in-game, automatically locking access doors during midnight alignments, or spawning world events consistently during scheduled holidays.

Use `?"` symbols inside arguments to define recurring wildcard matches (assigning an hour string as `?` causes the logic to execute at that specific minute interval every sequential hour).

[Table of Contents](./table_of_contents.md) | [Next: 10 Utilities & Advanced Topics](./10_utilities_advanced.md)
