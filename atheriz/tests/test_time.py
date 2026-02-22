"""
Extensive tests for atheriz.singletons.time.GameTime

Focuses on correctness of get_timespan and get_time under different
settings configurations, including fractional TICK_MINUTES values.
"""

import sys
import pytest
import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from pyatomix import AtomicInt

# ---------------------------------------------------------------------------
# Pre-mock heavy dependencies that cause circular imports when importing
# atheriz.singletons.time.  We only need the GameTime class itself and
# atheriz.settings — everything else (object system, websockets, utils)
# is irrelevant for these unit tests.
# ---------------------------------------------------------------------------
# Save original sys.modules state to prevent poisoning other tests
_mods_to_mock = [
    "atheriz.singletons.get",
    "atheriz.singletons.objects",
    "atheriz.utils",
    "atheriz.websocket",
    "atheriz.objects.persist",
    "atheriz.objects.session",
    "atheriz.objects.base_account",
    "atheriz.objects.base_obj",
]
_original_modules = {m: sys.modules.get(m) for m in _mods_to_mock}

for _mod in _mods_to_mock:
    if _mod == "atheriz.objects.base_obj":
        mod_mock = MagicMock()
        # Object needs to be a type for isinstance() checks to work
        mod_mock.Object = MagicMock
        sys.modules[_mod] = mod_mock
    elif _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import atheriz.settings as settings
from atheriz.singletons.time import GameTime

# RESTORE sys.modules immediately after import. GameTime has its references,
# and we stop poisoning the global state for other tests (like serialization).
for m, val in _original_modules.items():
    if val is None:
        if m in sys.modules:
            del sys.modules[m]
    else:
        sys.modules[m] = val

# ========================== Helpers / Fixtures ==============================

TEST_SAVE_DIR = Path("test_time_save_data")


@pytest.fixture(autouse=True)
def _clean_save_dir():
    """Ensure a clean save directory for every test."""
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)
    yield
    if TEST_SAVE_DIR.exists():
        shutil.rmtree(TEST_SAVE_DIR)


def _make_gt(ticks: int = 0) -> GameTime:
    """Create a GameTime instance with a given tick count, bypassing file IO."""
    with patch.object(GameTime, "load"):
        gt = GameTime()
    gt.ticks = AtomicInt(ticks)
    gt.alarms = {}
    return gt


# ========================== get_timespan ====================================


class TestGetTimespanDefaults:
    """Tests using the default settings (TICK_MINUTES=1.0)."""

    def test_zero_ticks(self):
        gt = _make_gt(0)
        result = gt.get_timespan(0)
        assert result["desc"] == "now"
        assert result["years"] == 0
        assert result["months"] == 0
        assert result["weeks"] == 0
        assert result["days"] == 0
        assert result["hours"] == 0
        assert result["minutes"] == 0

    def test_one_tick_is_one_minute(self):
        gt = _make_gt(0)
        result = gt.get_timespan(1)
        assert result["minutes"] == settings.TICK_MINUTES  # 1.0
        assert "minute" in result["desc"]

    def test_one_hour(self):
        """60 ticks @ 1 min/tick = 1 hour."""
        gt = _make_gt(0)
        ticks = int(settings.MINUTES_PER_HOUR / settings.TICK_MINUTES)
        result = gt.get_timespan(ticks)
        assert result["hours"] == 1
        assert result["minutes"] == 0
        assert "1 hour" in result["desc"]

    def test_one_day(self):
        ticks_per_hour = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        ticks = int(ticks_per_hour * settings.HOURS_PER_DAY)
        gt = _make_gt(0)
        result = gt.get_timespan(ticks)
        assert result["days"] == 1
        assert result["hours"] == 0
        assert "1 day" in result["desc"]

    def test_one_week(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        ticks = int(tph * settings.HOURS_PER_DAY * settings.DAYS_PER_WEEK)
        gt = _make_gt(0)
        result = gt.get_timespan(ticks)
        assert result["weeks"] == 1
        assert result["days"] == 0
        assert "1 week" in result["desc"]

    def test_one_month(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        ticks = int(tph * settings.HOURS_PER_DAY * settings.DAYS_PER_MONTH)
        gt = _make_gt(0)
        result = gt.get_timespan(ticks)
        assert result["months"] == 1
        assert result["weeks"] == 0
        assert "1 month" in result["desc"]

    def test_one_year(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        ticks = int(tpd * settings.DAYS_PER_MONTH * settings.MONTHS_PER_YEAR)
        gt = _make_gt(0)
        result = gt.get_timespan(ticks)
        assert result["years"] == 1
        assert result["months"] == 0
        assert "1 year" in result["desc"]

    def test_negative_ticks(self):
        gt = _make_gt(0)
        result = gt.get_timespan(-60)
        assert "in the future" in result["desc"]
        assert result["hours"] == 1

    def test_mixed_large_value(self):
        """13 months, 2 weeks, 3 days, 4 hours, 5 minutes → verify all buckets."""
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        tpw = tpd * settings.DAYS_PER_WEEK
        tpmo = tpd * settings.DAYS_PER_MONTH
        tpy = tpmo * settings.MONTHS_PER_YEAR
        ticks = int(1 * tpy + 1 * tpmo + 2 * tpw + 3 * tpd + 4 * tph + 5)
        gt = _make_gt(0)
        result = gt.get_timespan(ticks)
        assert result["years"] == 1
        assert result["months"] == 1
        assert result["weeks"] == 2
        assert result["days"] == 3
        assert result["hours"] == 4
        assert result["minutes"] == 5 * settings.TICK_MINUTES

    def test_plural_formatting(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        gt = _make_gt(0)
        result = gt.get_timespan(int(tph * 2))
        assert "2 hours" in result["desc"]

    def test_singular_formatting(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        gt = _make_gt(0)
        result = gt.get_timespan(int(tph))
        assert "1 hour" in result["desc"]

    def test_desc_contains_and_for_multiple_units(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        ticks = int(tpd + tph + 5)
        gt = _make_gt(0)
        result = gt.get_timespan(ticks)
        assert " and " in result["desc"]
        assert "ago" in result["desc"]


class TestGetTimespanFractionalTickMinutes:
    """Test get_timespan when TICK_MINUTES is fractional (e.g., 0.5, 0.25, 2.0)."""

    @pytest.fixture(autouse=True)
    def _save_restore_settings(self):
        """Save and restore TICK_MINUTES around each test."""
        original = settings.TICK_MINUTES
        yield
        settings.TICK_MINUTES = original

    def test_half_minute_ticks_zero(self):
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        result = gt.get_timespan(0)
        assert result["desc"] == "now"

    def test_half_minute_ticks_one_minute(self):
        """When TICK_MINUTES=0.5, it takes 2 ticks for 1 minute."""
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        # 2 ticks = 1 minute
        result = gt.get_timespan(2)
        assert result["minutes"] == pytest.approx(1.0)

    def test_half_minute_ticks_one_hour(self):
        """When TICK_MINUTES=0.5, takes 120 ticks for 1 hour."""
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES  # 120
        result = gt.get_timespan(int(tph))
        assert result["hours"] == 1
        assert result["minutes"] == pytest.approx(0)

    def test_half_minute_ticks_one_day(self):
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        result = gt.get_timespan(int(tpd))
        assert result["days"] == 1
        assert result["hours"] == 0

    def test_half_minute_ticks_partial(self):
        """3 ticks @ 0.5 min = 1.5 minutes → should show 1 minute leftover = 1.5."""
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        result = gt.get_timespan(3)
        assert result["minutes"] == pytest.approx(1.5)

    def test_quarter_minute_ticks_one_hour(self):
        """When TICK_MINUTES=0.25, it takes 240 ticks for 1 hour."""
        settings.TICK_MINUTES = 0.25
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES  # 240
        result = gt.get_timespan(int(tph))
        assert result["hours"] == 1
        assert result["minutes"] == pytest.approx(0)

    def test_quarter_minute_ticks_one_year(self):
        settings.TICK_MINUTES = 0.25
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        tpmo = tpd * settings.DAYS_PER_MONTH
        tpy = tpmo * settings.MONTHS_PER_YEAR
        result = gt.get_timespan(int(tpy))
        assert result["years"] == 1
        assert result["months"] == 0

    def test_double_minute_ticks_one_hour(self):
        """When TICK_MINUTES=2.0, 30 ticks = 1 hour."""
        settings.TICK_MINUTES = 2.0
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES  # 30
        result = gt.get_timespan(int(tph))
        assert result["hours"] == 1
        assert result["minutes"] == pytest.approx(0)

    def test_double_minute_ticks_mixed(self):
        """2 hours and 4 minutes at TICK_MINUTES=2.0."""
        settings.TICK_MINUTES = 2.0
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES  # 30
        # 2 hours = 60 ticks, 4 minutes = 2 ticks (2 * 2.0 = 4 min)
        ticks = int(2 * tph + 2)
        result = gt.get_timespan(ticks)
        assert result["hours"] == 2
        assert result["minutes"] == pytest.approx(4.0)

    def test_fractional_negative(self):
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        result = gt.get_timespan(-120)
        assert "in the future" in result["desc"]
        assert result["hours"] == 1

    def test_five_minute_ticks(self):
        """TICK_MINUTES=5 → 12 ticks per hour."""
        settings.TICK_MINUTES = 5.0
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES  # 12
        result = gt.get_timespan(int(tph))
        assert result["hours"] == 1
        result2 = gt.get_timespan(1)
        assert result2["minutes"] == pytest.approx(5.0)

    def test_tenth_minute_ticks_consistency(self):
        """TICK_MINUTES=0.1 → 600 ticks per hour. Verify full decomposition."""
        settings.TICK_MINUTES = 0.1
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES  # 600
        tpd = tph * settings.HOURS_PER_DAY  # 14400
        # 1 day, 2 hours, 30 minutes
        ticks = int(tpd + 2 * tph + 300)  # 300 ticks * 0.1 = 30 min
        result = gt.get_timespan(ticks)
        assert result["days"] == 1
        assert result["hours"] == 2
        assert result["minutes"] == pytest.approx(30.0)


# ========================== get_time ========================================


class TestGetTimeDefaults:
    """Tests for get_time with default settings (TICK_MINUTES=1.0)."""

    def test_tick_zero(self):
        gt = _make_gt(0)
        t = gt.get_time()
        assert t["year"] == settings.START_YEAR
        assert t["month"] == 1
        assert t["day"] == 1
        assert t["hour"] == 0
        assert t["minute"] == 0
        assert t["second"] == 0

    def test_one_tick_advances_one_minute(self):
        gt = _make_gt(1)
        t = gt.get_time()
        assert t["minute"] == 1

    def test_60_ticks_advances_one_hour(self):
        gt = _make_gt(60)
        t = gt.get_time()
        assert t["hour"] == 1
        assert t["minute"] == 0

    def test_full_day_ticks(self):
        ticks_per_day = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        gt = _make_gt(int(ticks_per_day))
        t = gt.get_time()
        assert t["day"] == 2
        assert t["hour"] == 0
        assert t["minute"] == 0

    def test_full_month_ticks(self):
        ticks_per_day = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks_per_month = ticks_per_day * settings.DAYS_PER_MONTH
        gt = _make_gt(int(ticks_per_month))
        t = gt.get_time()
        assert t["month"] == 2
        assert t["day"] == 1

    def test_full_year_ticks(self):
        ticks_per_day = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks_per_year = ticks_per_day * settings.DAYS_PER_YEAR
        gt = _make_gt(int(ticks_per_year))
        t = gt.get_time()
        assert t["year"] == settings.START_YEAR + 1
        assert t["month"] == 1
        assert t["day"] == 1

    def test_formatted_short_present(self):
        gt = _make_gt(0)
        t = gt.get_time()
        assert "formatted_short" in t
        assert str(settings.START_YEAR) in t["formatted_short"]

    def test_formatted_contains_moon(self):
        gt = _make_gt(0)
        t = gt.get_time()
        assert "Moon phase" in t["formatted"]

    def test_season_at_start_is_winter(self):
        """Month 1 (Ianuarius) should be winter."""
        gt = _make_gt(0)
        t = gt.get_time()
        assert t["season"] == "winter"

    def test_season_spring(self):
        """Month 3 = spring."""
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        # Jump to the start of month 3 (2 full months elapsed)
        ticks = int(tpd * settings.DAYS_PER_MONTH * 2)
        gt = _make_gt(ticks)
        t = gt.get_time()
        assert t["month"] == 3
        assert t["season"] == "spring"

    def test_season_summer(self):
        """Month 6 = summer."""
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks = int(tpd * settings.DAYS_PER_MONTH * 5)
        gt = _make_gt(ticks)
        t = gt.get_time()
        assert t["month"] == 6
        assert t["season"] == "summer"

    def test_season_autumn(self):
        """Month 9 = autumn."""
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks = int(tpd * settings.DAYS_PER_MONTH * 8)
        gt = _make_gt(ticks)
        t = gt.get_time()
        assert t["month"] == 9
        assert t["season"] == "autumn"

    def test_season_winter_december(self):
        """Month 12 = winter."""
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks = int(tpd * settings.DAYS_PER_MONTH * 11)
        gt = _make_gt(ticks)
        t = gt.get_time()
        assert t["month"] == 12
        assert t["season"] == "winter"

    def test_moon_phase_new(self):
        gt = _make_gt(0)
        t = gt.get_time()
        assert t["moon_phase"] == "new"

    def test_moon_phase_full(self):
        """Full moon at day 15 of the lunar cycle."""
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks = int(tpd * 15)
        gt = _make_gt(ticks)
        t = gt.get_time()
        assert t["moon_phase"] == "full"

    def test_moon_phase_cycles(self):
        """After a full lunar cycle (30 days), moon is new again."""
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        ticks = int(tpd * settings.LUNAR_CYCLE_DAYS)
        gt = _make_gt(ticks)
        t = gt.get_time()
        assert t["moon_phase"] == "new"

    def test_ordinal_day_suffixes(self):
        tpd = settings.MINUTES_PER_HOUR * settings.HOURS_PER_DAY
        # Day 1 → "1st"
        gt = _make_gt(0)
        assert "1st" in gt.get_time()["formatted"]
        # Day 2 → "2nd"
        gt = _make_gt(int(tpd))
        assert "2nd" in gt.get_time()["formatted"]
        # Day 3 → "3rd"
        gt = _make_gt(int(tpd * 2))
        assert "3rd" in gt.get_time()["formatted"]
        # Day 4 → "4th"
        gt = _make_gt(int(tpd * 3))
        assert "4th" in gt.get_time()["formatted"]
        # Day 11 → "11th" (special)
        gt = _make_gt(int(tpd * 10))
        assert "11th" in gt.get_time()["formatted"]
        # Day 21 → "21st"
        gt = _make_gt(int(tpd * 20))
        assert "21st" in gt.get_time()["formatted"]

    def test_week_of_season(self):
        gt = _make_gt(0)
        t = gt.get_time()
        assert t["week_of_season"] >= 1


class TestGetTimeFractionalTickMinutes:
    """Test get_time when TICK_MINUTES is fractional."""

    @pytest.fixture(autouse=True)
    def _save_restore_settings(self):
        original = settings.TICK_MINUTES
        yield
        settings.TICK_MINUTES = original

    def test_half_minute_tick_two_ticks_one_minute(self):
        """TICK_MINUTES=0.5 → 2 ticks advance 1 minute."""
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(2)
        t = gt.get_time()
        assert t["minute"] == 1

    def test_half_minute_tick_one_hour(self):
        """TICK_MINUTES=0.5 → 120 ticks = 1 hour."""
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(120)
        t = gt.get_time()
        assert t["hour"] == 1
        assert t["minute"] == 0

    def test_half_minute_tick_one_day(self):
        settings.TICK_MINUTES = 0.5
        ticks_per_day = (settings.MINUTES_PER_HOUR / 0.5) * settings.HOURS_PER_DAY
        gt = _make_gt(int(ticks_per_day))
        t = gt.get_time()
        assert t["day"] == 2
        assert t["hour"] == 0

    def test_quarter_minute_tick_one_hour(self):
        """TICK_MINUTES=0.25 → 240 ticks = 1 hour."""
        settings.TICK_MINUTES = 0.25
        gt = _make_gt(240)
        t = gt.get_time()
        assert t["hour"] == 1
        assert t["minute"] == 0

    def test_double_minute_tick(self):
        """TICK_MINUTES=2.0 → 1 tick = 2 minutes."""
        settings.TICK_MINUTES = 2.0
        gt = _make_gt(1)
        t = gt.get_time()
        assert t["minute"] == 2

    def test_double_minute_tick_one_hour(self):
        """TICK_MINUTES=2.0 → 30 ticks = 1 hour."""
        settings.TICK_MINUTES = 2.0
        gt = _make_gt(30)
        t = gt.get_time()
        assert t["hour"] == 1
        assert t["minute"] == 0

    def test_five_minute_tick_one_hour(self):
        """TICK_MINUTES=5 → 12 ticks = 1 hour."""
        settings.TICK_MINUTES = 5.0
        gt = _make_gt(12)
        t = gt.get_time()
        assert t["hour"] == 1
        assert t["minute"] == 0

    def test_fractional_full_year(self):
        """TICK_MINUTES=0.5 → verify a full year still works."""
        settings.TICK_MINUTES = 0.5
        tph = settings.MINUTES_PER_HOUR / 0.5
        tpd = tph * settings.HOURS_PER_DAY
        tpy = tpd * settings.DAYS_PER_YEAR
        gt = _make_gt(int(tpy))
        t = gt.get_time()
        assert t["year"] == settings.START_YEAR + 1
        assert t["month"] == 1
        assert t["day"] == 1

    def test_fractional_consistency_get_time_vs_get_timespan(self):
        """Verify get_time and get_timespan agree for the same tick count."""
        settings.TICK_MINUTES = 0.5
        tph = settings.MINUTES_PER_HOUR / 0.5
        tpd = tph * settings.HOURS_PER_DAY
        # 2 days, 3 hours, 10 minutes (= 20 ticks at 0.5)
        ticks = int(2 * tpd + 3 * tph + 20)
        gt = _make_gt(ticks)
        span = gt.get_timespan(ticks)
        time_dict = gt.get_time()

        assert span["days"] == 2
        assert span["hours"] == 3
        assert span["minutes"] == pytest.approx(10.0)
        assert time_dict["day"] == 3  # day 1 + 2 elapsed
        assert time_dict["hour"] == 3
        assert time_dict["minute"] == 10


# ========================== sun_up ==========================================


class TestSunUp:
    """Test sun_up and sun_up_alt methods."""

    def test_sun_up_at_sunrise(self):
        ticks = int(settings.SUNRISE_HOUR * settings.MINUTES_PER_HOUR)
        gt = _make_gt(ticks)
        assert gt.sun_up() is True

    def test_sun_down_at_midnight(self):
        gt = _make_gt(0)
        assert gt.sun_up() is False

    def test_sun_down_before_sunrise(self):
        ticks = int((settings.SUNRISE_HOUR - 1) * settings.MINUTES_PER_HOUR)
        gt = _make_gt(ticks)
        assert gt.sun_up() is False

    def test_sun_up_at_noon(self):
        ticks = int(12 * settings.MINUTES_PER_HOUR)
        gt = _make_gt(ticks)
        assert gt.sun_up() is True

    def test_sun_up_before_sunset(self):
        ticks = int((settings.SUNSET_HOUR - 1) * settings.MINUTES_PER_HOUR)
        gt = _make_gt(ticks)
        assert gt.sun_up() is True

    def test_sun_down_at_sunset(self):
        ticks = int(settings.SUNSET_HOUR * settings.MINUTES_PER_HOUR)
        gt = _make_gt(ticks)
        assert gt.sun_up() is False

    def test_sun_up_alt_directly(self):
        gt = _make_gt(0)
        assert gt.sun_up_alt(settings.SUNRISE_HOUR) is True
        assert gt.sun_up_alt(settings.SUNRISE_HOUR - 1) is False
        assert gt.sun_up_alt(settings.SUNSET_HOUR - 1) is True
        assert gt.sun_up_alt(settings.SUNSET_HOUR) is False
        assert gt.sun_up_alt(0) is False
        assert gt.sun_up_alt(12) is True


class TestSunUpFractional:
    """Sun state with fractional TICK_MINUTES."""

    @pytest.fixture(autouse=True)
    def _save_restore_settings(self):
        original = settings.TICK_MINUTES
        yield
        settings.TICK_MINUTES = original

    def test_sun_up_half_tick(self):
        """TICK_MINUTES=0.5, sunrise should still be sun-up."""
        settings.TICK_MINUTES = 0.5
        tph = settings.MINUTES_PER_HOUR / 0.5
        ticks = int(settings.SUNRISE_HOUR * tph)
        gt = _make_gt(ticks)
        assert gt.sun_up() is True

    def test_sun_down_half_tick(self):
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(0)
        assert gt.sun_up() is False


# ========================== Alarms ==========================================


class TestAlarms:
    """Test alarm add/remove logic (no actual tick execution)."""

    def test_add_alarm(self):
        gt = _make_gt(0)
        mock_obj = MagicMock()
        mock_obj.id = 42
        gt.add_alarm("6", "30", mock_obj)
        assert ("6", "30") in gt.alarms
        assert len(gt.alarms[("6", "30")]) == 1
        assert gt.alarms[("6", "30")][0][0] == 42

    def test_add_alarm_int_args_converted(self):
        gt = _make_gt(0)
        mock_obj = MagicMock()
        mock_obj.id = 99
        gt.add_alarm(6, 30, mock_obj)  # ints instead of strings
        assert ("6", "30") in gt.alarms

    def test_add_alarm_repeat_flag(self):
        gt = _make_gt(0)
        mock_obj = MagicMock()
        mock_obj.id = 1
        gt.add_alarm("12", "0", mock_obj, repeat=True)
        assert gt.alarms[("12", "0")][0][1] is True

    def test_add_alarm_with_data(self):
        gt = _make_gt(0)
        mock_obj = MagicMock()
        mock_obj.id = 1
        gt.add_alarm("0", "0", mock_obj, data={"key": "val"})
        assert gt.alarms[("0", "0")][0][2] == {"key": "val"}

    def test_add_alarm_none_caller(self):
        gt = _make_gt(0)
        gt.add_alarm("1", "1", None)
        assert len(gt.alarms) == 0

    def test_add_multiple_alarms_same_time(self):
        gt = _make_gt(0)
        obj1 = MagicMock()
        obj1.id = 1
        obj2 = MagicMock()
        obj2.id = 2
        gt.add_alarm("6", "0", obj1)
        gt.add_alarm("6", "0", obj2)
        assert len(gt.alarms[("6", "0")]) == 2

    def test_remove_alarm(self):
        gt = _make_gt(0)
        mock_obj = MagicMock()
        mock_obj.id = 42
        gt.add_alarm("6", "30", mock_obj)
        gt.remove_alarm("6", "30", mock_obj)
        assert len(gt.alarms[("6", "30")]) == 0

    def test_remove_alarm_by_id(self):
        gt = _make_gt(0)
        mock_obj = MagicMock()
        mock_obj.id = 42
        gt.add_alarm("6", "30", mock_obj)
        gt.remove_alarm("6", "30", 42)
        assert len(gt.alarms[("6", "30")]) == 0

    def test_remove_alarm_none_caller(self):
        gt = _make_gt(0)
        gt.remove_alarm("1", "1", None)  # should not crash

    def test_remove_alarm_nonexistent(self):
        gt = _make_gt(0)
        gt.remove_alarm("99", "99", 12345)  # should not crash

    def test_remove_alarms_by_caller(self):
        gt = _make_gt(0)
        obj = MagicMock()
        obj.id = 10
        gt.add_alarm("1", "0", obj)
        gt.add_alarm("2", "0", obj)
        gt.remove_alarms_by_caller(obj)
        # The tuples in the alarm lists should now be cleaned out
        for v in gt.alarms.values():
            for entry in v:
                assert entry[0] != 10


# ========================== Save / Load =====================================


class TestSaveLoad:
    """Test persistence of ticks and alarms."""

    def test_save_and_load(self):
        with patch("atheriz.settings.SAVE_PATH", str(TEST_SAVE_DIR)):
            gt = _make_gt(500)
            gt.alarms = {("6", "0"): [(1, True, None)]}
            gt.save()

            # Create a new instance and load
            with patch.object(GameTime, "load"):
                gt2 = GameTime()
            gt2.load()
            assert gt2.ticks.load() == 500

    def test_load_missing_file(self):
        """Loading when no save file exists should default to 0 ticks."""
        with patch("atheriz.settings.SAVE_PATH", str(TEST_SAVE_DIR / "nonexistent")):
            with patch.object(GameTime, "load"):
                gt = GameTime()
            gt.load()
            assert gt.ticks.load() == 0
            assert gt.alarms == {}


# ========================== Edge cases ======================================


class TestEdgeCases:
    """Various edge-case tests."""

    @pytest.fixture(autouse=True)
    def _save_restore_settings(self):
        original = settings.TICK_MINUTES
        yield
        settings.TICK_MINUTES = original

    def test_get_timespan_single_tick_various_rates(self):
        """Verify 1 tick always equals TICK_MINUTES minutes."""
        for tm in [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]:
            settings.TICK_MINUTES = tm
            gt = _make_gt(0)
            result = gt.get_timespan(1)
            assert result["minutes"] == pytest.approx(tm), f"Failed for TICK_MINUTES={tm}"

    def test_get_time_and_timespan_roundtrip_various_rates(self):
        """For several TICK_MINUTES values, get_time at a known tick and
        verify the hour/minute match what get_timespan computes."""
        for tm in [0.25, 0.5, 1.0, 2.0, 5.0]:
            settings.TICK_MINUTES = tm
            tph = settings.MINUTES_PER_HOUR / tm
            # 3 hours 16 minutes (196 minutes, divisible by 0.25, 0.5, 1, 2, but not 5)
            # We skip 5.0 for this exact check or ensure it divides evenly?
            # 196 / 5 = 39.2 -> not integer. 
            # 3 hours 20 minutes (200 minutes) divides by all safely.
            target_minutes = 3 * 60 + 20
            ticks = int(target_minutes / tm)
            gt = _make_gt(ticks)

            t = gt.get_time()
            assert t["hour"] == 3, f"Failed hour for TICK_MINUTES={tm}"
            assert t["minute"] == 20, f"Failed minute for TICK_MINUTES={tm}"

            span = gt.get_timespan(ticks)
            assert span["hours"] == 3, f"Failed span hours for TICK_MINUTES={tm}"
            assert span["minutes"] == pytest.approx(20.0), f"Failed span minutes for TICK_MINUTES={tm}"

    def test_very_large_tick_count(self):
        """10 years worth of ticks."""
        gt = _make_gt(0)
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        tpy = tpd * settings.DAYS_PER_YEAR
        ticks = int(10 * tpy)
        result = gt.get_timespan(ticks)
        assert result["years"] == 10

    def test_get_time_at_very_large_ticks(self):
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        tpy = tpd * settings.DAYS_PER_YEAR
        gt = _make_gt(int(10 * tpy))
        t = gt.get_time()
        assert t["year"] == settings.START_YEAR + 10

    def test_month_name_enum(self):
        gt = _make_gt(0)
        t = gt.get_time()
        assert "Ianuarius" in t["formatted"]

    def test_ticks_field_in_get_time(self):
        gt = _make_gt(42)
        t = gt.get_time()
        assert t["ticks"] == 42

    def test_get_timespan_small_fractional(self):
        """TICK_MINUTES=0.1 with a single tick = 0.1 minutes."""
        settings.TICK_MINUTES = 0.1
        gt = _make_gt(0)
        result = gt.get_timespan(1)
        assert result["minutes"] == pytest.approx(0.1)

    def test_get_time_seconds_field_nonzero(self):
        """With TICK_MINUTES=1, each tick is 60 real seconds, so the
        seconds field should always be 0 at exactly N ticks.
        But with TICK_MINUTES=0.5, each tick is 30 seconds, so odd
        ticks should give second=30."""
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(1)  # 0.5 minutes = 30 seconds
        t = gt.get_time()
        assert t["second"] == 30

    def test_get_time_seconds_zero_on_even_ticks(self):
        settings.TICK_MINUTES = 0.5
        gt = _make_gt(2)  # 1.0 minutes = 60 seconds → second wraps to 0
        t = gt.get_time()
        assert t["second"] == 0
        assert t["minute"] == 1


class TestTimeEvents:
    """Test solar and lunar events Triggering through at_solar_event and at_lunar_event."""
    
    @patch("atheriz.singletons.time.get_solar_receivers")
    @patch("atheriz.singletons.time.get_lunar_receivers")
    def test_solar_events(self, mock_lunar, mock_solar):
        mock_character = MagicMock()
        mock_solar.return_value = [mock_character]
        mock_lunar.return_value = []
        
        # Start exactly at sunrise - 1 tick
        ticks_before_sunrise = int(settings.SUNRISE_HOUR * settings.MINUTES_PER_HOUR) - int(settings.TICK_MINUTES)
        gt = _make_gt(ticks_before_sunrise)
        
        # Next tick crosses sunrise
        gt.on_tick()
        mock_character.at_solar_event.assert_called_with(settings.SUNRISE_MESSAGE)
        
        # Reset mock
        mock_character.reset_mock()
        
        # Start exactly at sunset - 1 tick
        ticks_before_sunset = int(settings.SUNSET_HOUR * settings.MINUTES_PER_HOUR) - int(settings.TICK_MINUTES)
        gt = _make_gt(ticks_before_sunset)
        
        # Next tick crosses sunset
        gt.on_tick()
        mock_character.at_solar_event.assert_called_with(settings.SUNSET_MESSAGE)

    @patch("atheriz.singletons.time.get_solar_receivers")
    @patch("atheriz.singletons.time.get_lunar_receivers")
    def test_lunar_events(self, mock_lunar, mock_solar):
        mock_character = MagicMock()
        mock_solar.return_value = []
        mock_lunar.return_value = [mock_character]
        
        # Start right at the end of day 0 (New moon)
        # Phase changes to Waxing Crescent on day 1
        tph = settings.MINUTES_PER_HOUR / settings.TICK_MINUTES
        tpd = tph * settings.HOURS_PER_DAY
        ticks_before_change = int(tpd) - 1
        
        gt = _make_gt(ticks_before_change)
        before_phase = gt.get_time()["moon_phase"]
        
        # Next tick crosses into day 1
        gt.on_tick()
        after_phase = gt.get_time()["moon_phase"]
        
        assert before_phase == "new"
        assert after_phase == "waxing crescent"
        mock_character.at_lunar_event.assert_called_with(f"A {after_phase.lower()} moon rises.")
