from typing import TYPE_CHECKING, Any
import atheriz.settings as settings
from threading import RLock
from pyatomix import AtomicInt
from pathlib import Path
from atheriz.singletons.get import get_async_ticker, get_async_threadpool
from atheriz.singletons.objects import get
from atheriz.utils import msg_all
import json
import ast
from atheriz.objects.base_obj import Object


class GameTime:
    def save(self) -> None:
        path = Path(settings.SAVE_PATH) / "time"
        path.parent.mkdir(parents=True, exist_ok=True)
        alarms_data = {str(k): v for k, v in self.alarms.items()}
        with open(path, "w") as f:
            json.dump({"ticks": self.ticks.load(), "alarms": alarms_data}, f)

    def load(self) -> None:
        path = Path(settings.SAVE_PATH) / "time"
        if not path.exists():
            self.ticks = AtomicInt(0)
            self.alarms: dict[tuple[str, str], list[tuple[int, bool, Any]]] = {}
            return
        with open(path, "r") as f:
            data = json.load(f)
            self.ticks = AtomicInt(data["ticks"])
            self.alarms = {}
            for k, v in data["alarms"].items():
                try:
                    key = ast.literal_eval(k)
                    if isinstance(key, tuple) and len(key) == 2:
                        self.alarms[key] = v
                except (ValueError, SyntaxError):
                    print(f"Error parsing alarm key: {k}")
                    pass

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
            data (Any, optional): data to pass to at_alarm(). Defaults to None.
        """
        if not caller:
            return
        if not isinstance(hour, str):
            hour = str(hour)
        if not isinstance(minute, str):
            minute = str(minute)
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
        if not caller:
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

    def start(self) -> None:
        if not self.started:
            t = get_async_ticker()
            t.add_coro(self.on_tick, settings.TIME_UPDATE_SECONDS)
            self.started = True

    def sun_up(self) -> bool:
        time = self.get_time()
        hour = time["hour"]
        return hour >= 6 and hour < 18

    def sun_up_alt(self, hour: int) -> bool:
        return hour >= 6 and hour < 18

    def on_tick(self) -> None:
        before_time = self.get_time()
        before_sun = self.sun_up_alt(before_time["hour"])
        before_phase = before_time["moon_phase"]
        self.ticks += 1
        after_time = self.get_time()
        callers = []
        with self.lock:
            # there's an alarm that matches this exact hour and minute
            c = self.alarms.get((str(after_time["hour"]), str(after_time["minute"])))
            if c:
                callers.extend(c)
            # alarms that match (?, minute) go off every hour at the same minute
            c = self.alarms.get(("?", str(after_time["minute"])))
            if c:
                callers.extend(c)
            # alarms that match (hour, ?) go off every minute for that hour
            c = self.alarms.get((str(after_time["hour"]), "?"))
            if c:
                callers.extend(c)
        if callers:
            atp = get_async_threadpool()
            for id, repeat, data in callers:
                if not repeat:
                    self.remove_alarm(after_time["hour"], after_time["minute"], id)
                obj = get(id)
                if obj:
                    func = getattr(obj, "at_alarm")  # at_alarm(self, time, data)
                    atp.add_task(func, after_time, data)
                else:
                    print(f"obj not found for alarm: {id}")
        after_sun = self.sun_up_alt(after_time["hour"])
        after_phase = after_time["moon_phase"]
        if before_phase != after_phase:
            msg_all(f"A {after_phase.lower()} moon rises.")
        if before_sun != after_sun:
            if after_sun:
                msg_all("The sun rises on a new day.")
            else:
                msg_all("The sun begins to set.")

    def get_timespan(self, ticks: int) -> dict:
        """Convert ticks into human readable timespan, even negative ticks

        Args:
            ticks (int): duh

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
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
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
            y = leftover // tpy
            formatted = f"{y:.0f} years" if y > 1 else "1 year"
            leftover %= y * tpy
        if leftover >= tpmo:
            if formatted != "":
                formatted += ", "
            m = leftover // tpmo
            formatted += f"{m:.0f} months" if m > 1 else "1 month"
            leftover %= m * tpmo
        if leftover >= tpw:
            if formatted != "":
                formatted += ", "
            w = leftover // tpw
            formatted += f"{w:.0f} weeks" if w > 1 else "1 week"
            leftover %= w * tpw
        if leftover >= tpd:
            if formatted != "":
                formatted += ", "
            d = leftover // tpd
            formatted += f"{d:.0f} days" if d > 1 else "1 day"
            leftover %= d * tpd
        if leftover >= tph:
            if formatted != "":
                formatted += ", "
            h = leftover // tph
            formatted += f"{h:.0f} hours" if h > 1 else "1 hour"
            leftover %= h * tph
        if leftover > 0:
            if formatted != "":
                formatted += ", "
            formatted += f"{leftover * settings.TICK_MINUTES:.0f} minutes"
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
            "minutes": leftover * settings.TICK_MINUTES,
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

        current_ticks = self.ticks.load()
        tick_duration_seconds = int(settings.TICK_MINUTES * settings.SECONDS_PER_MINUTE)
        total_seconds_elapsed = current_ticks * tick_duration_seconds
        total_days_elapsed = total_seconds_elapsed // settings.SECONDS_PER_DAY

        remaining_seconds_in_day = total_seconds_elapsed % settings.SECONDS_PER_DAY
        calc_hour = remaining_seconds_in_day // settings.SECONDS_PER_HOUR
        remaining_seconds_in_hour = remaining_seconds_in_day % settings.SECONDS_PER_HOUR
        calc_minute = remaining_seconds_in_hour // settings.SECONDS_PER_MINUTE
        calc_second = remaining_seconds_in_hour % settings.SECONDS_PER_MINUTE

        calc_year_offset: int = total_days_elapsed // settings.DAYS_PER_YEAR
        day_of_year: int = total_days_elapsed % settings.DAYS_PER_YEAR
        calc_month: int = day_of_year // settings.DAYS_PER_MONTH
        calc_day = day_of_year % settings.DAYS_PER_MONTH
        day_in_lunar_cycle = total_days_elapsed % settings.LUNAR_CYCLE_DAYS
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
