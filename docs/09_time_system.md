# 09 The Time System

## 9.1 How Time Works

### 9.1.1 The Game Clock
Atheriz separates internal game time from server uptime. Every `TIME_UPDATE_SECONDS` real-world seconds, the game clock advances by `TICK_MINUTES` in-game minutes.

The calendar logic (days per month, months per year, hours per day) is defined in `atheriz/globals/time.py`. By default, 1 real second equals 1 game minute. This means 1 real hour represents 60 game hours (2.5 game days). All time-related settings can be overridden in `settings.py`.

## 9.2 Solar & Lunar Events

### 9.2.1 Sunrise & Sunset
When the game clock reaches `SUNRISE_HOUR` or `SUNSET_HOUR`, the server executes the `at_solar_event(msg)` hook on all objects that match the `SOLAR_RECEIVER_LAMBDA` filter.

The default lambda filters for connected players. To include NPCs, override the lambda in `settings.py`:
```python
SOLAR_RECEIVER_LAMBDA = lambda x: (x.is_pc and x.is_connected) or x.is_npc
```

### 9.2.2 Moon Phases
The variable `LUNAR_CYCLE_DAYS` controls the length of the lunar cycle. When the phase changes, the `at_lunar_event(msg)` hook fires on objects matching the `LUNAR_RECEIVER_LAMBDA` filter. This is useful for scheduling specific events, such as NPC behavior changes during a full moon.

## 9.3 Ticks & Alarms

### 9.3.1 The Tick System
Objects with `is_tickable = True` receive `at_tick()` calls every `tick_seconds`. 

Rooms (Nodes) also support the ticking system. To implement recurring mechanics (e.g., an NPC that wanders every 5 seconds), set `is_tickable = True`, define `tick_seconds = 5`, and override the `at_tick()` method on the object class.

### 9.3.2 Alarms
The `at_alarm(time, data)` hook schedules callbacks for specific in-game times. Use the time format dictionary provided in `atheriz/globals/time.py` to target exact dates or recurring daily hours (e.g., opening a shop at 8 AM in-game time).

[Table of Contents](./table_of_contents.md) | [Next: 10 Utilities & Advanced Topics](./10_utilities_advanced.md)
