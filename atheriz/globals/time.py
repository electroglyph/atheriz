from __future__ import annotations
from typing import TYPE_CHECKING, Any
import atheriz.settings as settings
from threading import RLock
from pathlib import Path
from atheriz.globals.get import get_async_ticker, get_async_threadpool
from atheriz.globals.objects import get, filter_by
from atheriz.database_setup import get_database
from atheriz.logger import logger
import json
import ast
import os
import dill
from fractions import Fraction
from atheriz.objects.base_obj import Object


class GameTime:
    def _ensure_table(self) -> None:
        db = get_database()
        with db.lock:
            db.connection.cursor().execute(
                "CREATE TABLE IF NOT EXISTS gametime (id INTEGER PRIMARY KEY, data BLOB)"
            )

    def save(self) -> None:
        self._ensure_table()
        db = get_database()
        with self.lock:
            blob = dill.dumps({"ticks": self.ticks, "alarms": self.alarms})
        with db.lock:
            cursor = db.connection.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO gametime (id, data) VALUES (0, ?)", (blob,)
            )

    def load(self) -> None:
        self._ensure_table()
        db = get_database()
        with db.lock:
            cursor = db.connection.cursor()
            cursor.execute("SELECT data FROM gametime WHERE id = 0")
            row = cursor.fetchone()
        if row is None:
            if self._load_legacy_file():
                return
            with self.lock:
                self.ticks = 0
                self.alarms: dict[tuple[str, str], list[tuple[int, bool, Any]]] = {}
            return
        try:
            data = dill.loads(row[0])
        except Exception as e:
            logger.warning(f"Corrupt gametime row, resetting to defaults: {e}")
            with self.lock:
                self.ticks = 0
                self.alarms = {}
            return
        with self.lock:
            self.ticks = data["ticks"]
            self.alarms = data["alarms"]

    def _load_legacy_file(self) -> bool:
        path = Path(settings.SAVE_PATH) / "time"
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Corrupt time file, resetting to defaults: {e}")
            return False
        with self.lock:
            self.ticks = data.get("ticks", 0)
            self.alarms = {}
            for k, v in data.get("alarms", {}).items():
                try:
                    key = ast.literal_eval(k)
                    if isinstance(key, tuple) and len(key) == 2:
                        cleaned = []
                        for id, repeat, adata in v:
                            if adata is None or isinstance(adata, dict):
                                cleaned.append((id, repeat, adata))
                            else:
                                logger.warning(f"Skipping alarm with non-dict data: {k}")
                        if cleaned:
                            self.alarms[key] = cleaned
                except (ValueError, SyntaxError):
                    logger.warning(f"Error parsing alarm key: {k}")
                    pass
        try:
            self.save()
        except Exception as e:
            logger.warning(f"Legacy time file migration to database failed: {e}")
            return False
        try:
            os.remove(path)
        except OSError:
            pass
        return True

    def __init__(self) -> None:
        self.lock = RLock()
        self.started = False
        self.load()

    def add_alarm(self, hour: str, minute: str, caller: Object, repeat=False, data=None) -> None:
        """
        add alarm

        Args:
            hour (str): hour
            minute (str): minute
            caller (Object): obj to add alarm to
            repeat (bool, optional): if True, repeat forever. Defaults to False.
            data (dict, optional): data to pass to at_alarm(). Defaults to None.
        """
        if not caller:
            return
        if not isinstance(hour, str):
            hour = str(hour)
        if not isinstance(minute, str):
            minute = str(minute)
        if data is not None and not isinstance(data, dict):
            raise TypeError(f"alarm data must be a dict or None, got {type(data).__name__}")
        with self.lock:
            a = self.alarms.get((hour, minute))
            if a:
                a.append((caller.id, repeat, data))
            else:
                self.alarms[(hour, minute)] = [(caller.id, repeat, data)]

    def remove_alarms_by_caller(self, caller: int | Object):
        if isinstance(caller, Object):
            caller = caller.id
        with self.lock:
            for v in self.alarms.values():
                for i in range(len(v) - 1, -1, -1):
                    if v[i][0] == caller:
                        del v[i]

    def remove_alarm(self, hour: str, minute: str, caller: int | Object) -> None:
        """
        remove alarm

        Args:
            hour (int): hour
            minute (int): minute
            caller (Object | int): object which has the alarm set or pk
        """
        if caller is None:
            return
        if isinstance(caller, Object):
            caller = caller.id
        if not isinstance(hour, str):
            hour = str(hour)
        if not isinstance(minute, str):
            minute = str(minute)
        with self.lock:
            a: list | None = self.alarms.get((hour, minute))
            if a:
                d = None
                for i, v in enumerate(a):
                    if v[0] == caller:
                        d = i
                        break
                if d is not None:
                    del a[d]

    def stop(self):
        t = get_async_ticker()
        t.remove_coro(self.on_tick, settings.TIME_UPDATE_SECONDS)
        self.save()
        self.started = False

    def start(self) -> None:
        if not self.started:
            t = get_async_ticker()
            t.add_coro(self.on_tick, settings.TIME_UPDATE_SECONDS)
            self.started = True

    def sun_up(self) -> bool:
        time = self.get_time()
        hour = time["hour"]
        return hour >= settings.SUNRISE_HOUR and hour < settings.SUNSET_HOUR

    def sun_up_alt(self, hour: int) -> bool:
        return hour >= settings.SUNRISE_HOUR and hour < settings.SUNSET_HOUR

    def on_tick(self) -> None:
        before_time = self.get_time()
        before_sun = self.sun_up_alt(before_time["hour"])
        before_phase = before_time["moon_phase"]
        with self.lock:
            self.ticks += 1
        after_time = self.get_time()
        callers = []
        with self.lock:
            # there's an alarm that matches this exact hour and minute
            c = self.alarms.get((str(after_time["hour"]), str(after_time["minute"])))
            if c:
                callers.extend(
                    ((str(after_time["hour"]), str(after_time["minute"])), id, repeat, data)
                    for id, repeat, data in c
                )
            # alarms that match (?, minute) go off every hour at the same minute
            c = self.alarms.get(("?", str(after_time["minute"])))
            if c:
                callers.extend(
                    (("?", str(after_time["minute"])), id, repeat, data)
                    for id, repeat, data in c
                )
            # alarms that match (hour, ?) go off every minute for that hour
            c = self.alarms.get((str(after_time["hour"]), "?"))
            if c:
                callers.extend(
                    ((str(after_time["hour"]), "?"), id, repeat, data)
                    for id, repeat, data in c
                )
        if callers:
            atp = get_async_threadpool()
            for key, id, repeat, data in callers:
                if not repeat:
                    self.remove_alarm(key[0], key[1], id)
                objs = get(id)
                if objs:
                    func = getattr(objs[0], "at_alarm")
                    if not atp.add_task(func, after_time, data):
                        logger.warning(f"Task queue full; alarm for {objs[0]} retrying.")
                        import time as _time

                        _time.sleep(0.05)
                        if not atp.add_task(func, after_time, data):
                            logger.warning(
                                f"Task queue still full; running alarm inline for {objs[0]}"
                            )
                            try:
                                func(after_time, data)
                            except Exception:
                                logger.error(
                                    f"Error in inline alarm for {objs[0]}",
                                    exc_info=True,
                                )
                else:
                    logger.warning(f"obj not found for alarm: {id}")
        after_sun = self.sun_up_alt(after_time["hour"])
        after_phase = after_time["moon_phase"]
        if before_phase != after_phase:
            for obj in filter_by(settings.LUNAR_RECEIVER_LAMBDA):
                obj.at_lunar_event(f"A {after_phase.lower()} moon rises.")
        if before_sun != after_sun:
            if after_sun:
                for obj in filter_by(settings.SOLAR_RECEIVER_LAMBDA):
                    obj.at_solar_event(settings.SUNRISE_MESSAGE)
            else:
                for obj in filter_by(settings.SOLAR_RECEIVER_LAMBDA):
                    obj.at_solar_event(settings.SUNSET_MESSAGE)

    def get_timespan(self, ticks: int) -> dict:
        """Convert ticks into human readable timespan, even negative ticks

        Args:
            ticks (int): elapsed ticks

        Returns:
            dict: years, months, weeks, days, hours, minutes, and desc = text
        """
        if ticks == 0:
            return {
                "years": 0,
                "months": 0,
                "weeks": 0,
                "days": 0,
                "hours": 0,
                "minutes": 0,
                "desc": "now",
            }
        last_word = "ago"
        if ticks < 0:
            last_word = "in the future"
            ticks *= -1
        leftover = ticks
        tick_minutes = Fraction(str(settings.TICK_MINUTES))
        tph = Fraction(settings.MINUTES_PER_HOUR, 1) / tick_minutes
        tpd = tph * settings.HOURS_PER_DAY
        tpw = tpd * settings.DAYS_PER_WEEK
        tpmo = tpd * settings.DAYS_PER_MONTH
        tpy = tpmo * settings.MONTHS_PER_YEAR
        formatted = ""
        y = 0
        m = 0
        w = 0
        d = 0
        h = 0
        if leftover >= tpy:
            y = int(leftover // tpy)
            formatted = f"{y:.0f} years" if y > 1 else "1 year"
            leftover %= Fraction(y) * tpy
        if leftover >= tpmo:
            if formatted != "":
                formatted += ", "
            m = int(leftover // tpmo)
            formatted += f"{m:.0f} months" if m > 1 else "1 month"
            leftover %= Fraction(m) * tpmo
        if leftover >= tpw:
            if formatted != "":
                formatted += ", "
            w = int(leftover // tpw)
            formatted += f"{w:.0f} weeks" if w > 1 else "1 week"
            leftover %= Fraction(w) * tpw
        if leftover >= tpd:
            if formatted != "":
                formatted += ", "
            d = int(leftover // tpd)
            formatted += f"{d:.0f} days" if d > 1 else "1 day"
            leftover %= Fraction(d) * tpd
        if leftover >= tph:
            if formatted != "":
                formatted += ", "
            h = int(leftover // tph)
            formatted += f"{h:.0f} hours" if h > 1 else "1 hour"
            leftover %= Fraction(h) * tph
        if leftover > 0:
            if formatted != "":
                formatted += ", "
            leftover_minutes = leftover * tick_minutes
            formatted += f"{float(leftover_minutes):.0f} minutes"
        comma = formatted.rfind(",")
        if comma > 0:
            desc = f"{formatted[:comma]} and{formatted[comma+1:]} {last_word}"
        else:
            desc = f"{formatted} {last_word}"
        return {
            "years": y,
            "months": m,
            "weeks": w,
            "days": d,
            "hours": h,
            "minutes": float(leftover * tick_minutes),
            "desc": desc,
        }

    def get_time(self) -> dict:
        """Get current time as a dict

        Returns:
            dict: year, month, day, hour, minute, second, moon_phase, formatted, season, weak_of_season, ticks
        """

        def ordinal_day(day: int) -> str:
            if 11 <= day <= 13:
                suffix = "th"
            else:
                last_digit = day % 10
                if last_digit == 1:
                    suffix = "st"
                elif last_digit == 2:
                    suffix = "nd"
                elif last_digit == 3:
                    suffix = "rd"
                else:
                    suffix = "th"
            return f"{day}{suffix}"

        with self.lock:
            current_ticks = self.ticks
        tick_duration_seconds = float(settings.TICK_MINUTES * settings.SECONDS_PER_MINUTE)
        total_seconds_elapsed = current_ticks * tick_duration_seconds
        total_days_elapsed = int(total_seconds_elapsed // settings.SECONDS_PER_DAY)

        remaining_seconds_in_day = total_seconds_elapsed % settings.SECONDS_PER_DAY
        calc_hour = int(remaining_seconds_in_day // settings.SECONDS_PER_HOUR)
        remaining_seconds_in_hour = remaining_seconds_in_day % settings.SECONDS_PER_HOUR
        calc_minute = int(remaining_seconds_in_hour // settings.SECONDS_PER_MINUTE)
        calc_second = int(remaining_seconds_in_hour % settings.SECONDS_PER_MINUTE)

        calc_year_offset: int = int(total_days_elapsed // settings.DAYS_PER_YEAR)
        day_of_year: int = int(total_days_elapsed % settings.DAYS_PER_YEAR)
        calc_month: int = int(day_of_year // settings.DAYS_PER_MONTH)
        calc_day = int(day_of_year % settings.DAYS_PER_MONTH)
        day_in_lunar_cycle = int(total_days_elapsed % settings.LUNAR_CYCLE_DAYS)
        moon_phase = ""

        if day_in_lunar_cycle == 0:
            moon_phase = "new"
        elif 1 <= day_in_lunar_cycle <= 6:
            moon_phase = "waxing crescent"
        elif day_in_lunar_cycle == 7:
            moon_phase = "first quarter"
        elif 8 <= day_in_lunar_cycle <= 14:
            moon_phase = "waxing gibbous"
        elif day_in_lunar_cycle == 15:
            moon_phase = "full"
        elif 16 <= day_in_lunar_cycle <= 21:
            moon_phase = "waning gibbous"
        elif day_in_lunar_cycle == 22:
            moon_phase = "third quarter"
        elif day_in_lunar_cycle >= 23:
            moon_phase = "waning crescent"

        final_year = settings.START_YEAR + calc_year_offset
        final_month: int = calc_month + 1
        final_day = calc_day + 1
        current_season_name = ""
        day_in_season = 0

        if 3 <= final_month <= 5:
            current_season_name = "spring"
            season_start_day_offset = (3 - 1) * settings.DAYS_PER_MONTH
            day_in_season = day_of_year - season_start_day_offset
        elif 6 <= final_month <= 8:
            current_season_name = "summer"
            season_start_day_offset = (6 - 1) * settings.DAYS_PER_MONTH
            day_in_season = day_of_year - season_start_day_offset
        elif 9 <= final_month <= 11:
            current_season_name = "autumn"
            season_start_day_offset = (9 - 1) * settings.DAYS_PER_MONTH
            day_in_season = day_of_year - season_start_day_offset
        else:
            current_season_name = "winter"
            winter_start_day_of_year = (12 - 1) * settings.DAYS_PER_MONTH
            if final_month == 12:
                # for month 12, it's days elapsed since winter start day in the current year
                day_in_season = day_of_year - winter_start_day_of_year
            else:  # for months 1 and 2
                days_in_winter_last_year = settings.DAYS_PER_YEAR - winter_start_day_of_year
                day_in_season = days_in_winter_last_year + day_of_year

        week_of_season = (day_in_season // settings.DAYS_PER_WEEK) + 1
        formatted_time = f"{calc_hour:02d}:{calc_minute:02d}:{calc_second:02d}"
        month_name = settings.Month(int(final_month)).name
        formatted_date_time = (
            f"{formatted_time}, {ordinal_day(final_day)} of {month_name}, year {final_year}\nWeek {week_of_season} of"
            f" {current_season_name}\nMoon phase: {moon_phase}"
        )
        formatted_short = (
            f"{formatted_time}, {ordinal_day(final_day)} of {month_name}, year {final_year}"
        )

        return {
            "year": final_year,
            "month": final_month,
            "day": final_day,
            "hour": calc_hour,
            "minute": calc_minute,
            "second": calc_second,
            "moon_phase": moon_phase,
            "formatted": formatted_date_time,
            "formatted_short": formatted_short,
            "season": current_season_name,
            "week_of_season": week_of_season,
            "ticks": current_ticks,
        }
