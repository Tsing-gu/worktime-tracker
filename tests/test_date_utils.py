"""
test_date_utils - 日期工具单元测试
====================================

覆盖 src/utils/date_utils.py 的所有公开函数，重点测试边界条件：
- compute_work_date：6:00 工作日窗口归属
- get_week_range：周边界
- get_month_range：月边界（含跨年）
- is_workday / is_rest_day：工作日判定（含节假日 + 调休）
- get_period_range：本期区间（连续非工作日段之间）
- get_previous_workday：前一个工作日
"""

from __future__ import annotations

from datetime import date, datetime

from src.utils.date_utils import (
    compute_work_date,
    get_month_range,
    get_period_range,
    get_previous_workday,
    get_week_range,
    is_rest_day,
    is_workday,
)


class TestComputeWorkDate:
    """compute_work_date：6:00 工作日窗口归属。"""

    def test_noon_belongs_to_today(self) -> None:
        """12:00 归属当天。"""
        ts = datetime(2026, 7, 15, 12, 0, 0)
        assert compute_work_date(ts) == date(2026, 7, 15)

    def test_before_6am_belongs_to_previous_day(self) -> None:
        """05:59 归属前一天。"""
        ts = datetime(2026, 7, 15, 5, 59, 59)
        assert compute_work_date(ts) == date(2026, 7, 14)

    def test_exactly_6am_belongs_to_today(self) -> None:
        """06:00 整归属当天（边界值）。"""
        ts = datetime(2026, 7, 15, 6, 0, 0)
        assert compute_work_date(ts) == date(2026, 7, 15)

    def test_just_before_6am_at_boundary(self) -> None:
        """05:59:59 归属前一天（边界值）。"""
        ts = datetime(2026, 7, 15, 5, 59, 59)
        assert compute_work_date(ts) == date(2026, 7, 14)

    def test_midnight_belongs_to_previous_day(self) -> None:
        """00:00 归属前一天。"""
        ts = datetime(2026, 7, 15, 0, 0, 0)
        assert compute_work_date(ts) == date(2026, 7, 14)

    def test_late_night_belongs_to_previous_day(self) -> None:
        """23:59 归属当天（工作日窗口到次日6:00）。"""
        ts = datetime(2026, 7, 15, 23, 59, 59)
        assert compute_work_date(ts) == date(2026, 7, 15)


class TestGetWeekRange:
    """get_week_range：周边界。"""

    def test_monday_is_start_of_week(self) -> None:
        """周一是一周的起始。"""
        # 2026-07-13 是周一
        start, end = get_week_range(date(2026, 7, 13))
        assert start == date(2026, 7, 13)
        assert end == date(2026, 7, 19)

    def test_sunday_is_end_of_week(self) -> None:
        """周日是一周的结束。"""
        # 2026-07-19 是周日
        start, end = get_week_range(date(2026, 7, 19))
        assert start == date(2026, 7, 13)
        assert end == date(2026, 7, 19)

    def test_midweek_day(self) -> None:
        """周三在周中间。"""
        # 2026-07-15 是周三
        start, end = get_week_range(date(2026, 7, 15))
        assert start == date(2026, 7, 13)
        assert end == date(2026, 7, 19)

    def test_week_starts_sunday(self) -> None:
        """week_start=0（周日为起始）。"""
        # 2026-07-15 周三，若周日为起始，则周范围是 7/12-7/18
        start, end = get_week_range(date(2026, 7, 15), week_start=0)
        assert start == date(2026, 7, 12)
        assert end == date(2026, 7, 18)


class TestGetMonthRange:
    """get_month_range：月边界。"""

    def test_normal_month(self) -> None:
        """普通月份（31天）。"""
        start, end = get_month_range(date(2026, 7, 15))
        assert start == date(2026, 7, 1)
        assert end == date(2026, 7, 31)

    def test_february_normal_year(self) -> None:
        """2月平年（28天）。"""
        start, end = get_month_range(date(2027, 2, 15))
        assert start == date(2027, 2, 1)
        assert end == date(2027, 2, 28)

    def test_december_cross_year(self) -> None:
        """12月（跨年边界，31天）。"""
        start, end = get_month_range(date(2026, 12, 15))
        assert start == date(2026, 12, 1)
        assert end == date(2026, 12, 31)

    def test_first_day_of_month(self) -> None:
        """月初。"""
        start, end = get_month_range(date(2026, 7, 1))
        assert start == date(2026, 7, 1)
        assert end == date(2026, 7, 31)

    def test_last_day_of_month(self) -> None:
        """月末。"""
        start, end = get_month_range(date(2026, 7, 31))
        assert start == date(2026, 7, 1)
        assert end == date(2026, 7, 31)


class TestIsWorkday:
    """is_workday：工作日判定。"""

    def test_weekday_monday_to_friday(self) -> None:
        """周一到周五是工作日（无节假日覆盖）。"""
        holidays: list[dict] = []
        for d in [
            date(2026, 7, 13),
            date(2026, 7, 14),
            date(2026, 7, 15),
            date(2026, 7, 16),
            date(2026, 7, 17),
        ]:
            assert is_workday(d, holidays, weekly_work_days=5) is True

    def test_weekend_saturday_sunday(self) -> None:
        """周六日非工作日（weekly_work_days=5）。"""
        holidays: list[dict] = []
        assert is_workday(date(2026, 7, 18), holidays, weekly_work_days=5) is False  # 周六
        assert is_workday(date(2026, 7, 19), holidays, weekly_work_days=5) is False  # 周日

    def test_holiday_off_day(self, sample_holidays: list[dict]) -> None:
        """法定放假日非工作日。"""
        # 2026-01-01 元旦
        assert is_workday(date(2026, 1, 1), sample_holidays, weekly_work_days=5) is False

    def test_holiday_adjusted_workday(self, sample_holidays: list[dict]) -> None:
        """调休补班日是工作日（周末补班）。"""
        # 2026-01-24 春节调休（周六补班）
        assert is_workday(date(2026, 1, 24), sample_holidays, weekly_work_days=5) is True

    def test_weekly_work_days_6(self) -> None:
        """weekly_work_days=6，周六是工作日。"""
        holidays: list[dict] = []
        assert is_workday(date(2026, 7, 18), holidays, weekly_work_days=6) is True  # 周六
        assert is_workday(date(2026, 7, 19), holidays, weekly_work_days=6) is False  # 周日

    def test_weekly_work_days_7(self) -> None:
        """weekly_work_days=7，全周都是工作日。"""
        holidays: list[dict] = []
        assert is_workday(date(2026, 7, 18), holidays, weekly_work_days=7) is True  # 周六
        assert is_workday(date(2026, 7, 19), holidays, weekly_work_days=7) is True  # 周日

    def test_dict_holiday_index(self, sample_holidays: list[dict]) -> None:
        """holidays 参数支持 dict 索引（build_holiday_index 构造）。"""
        from src.utils.date_utils import build_holiday_index

        h_index = build_holiday_index(sample_holidays)
        assert is_workday(date(2026, 1, 1), h_index, weekly_work_days=5) is False
        assert is_workday(date(2026, 1, 24), h_index, weekly_work_days=5) is True


class TestIsRestDay:
    """is_rest_day：休息日判定（is_workday 的反操作）。"""

    def test_weekday_is_not_rest(self) -> None:
        """工作日不是休息日。"""
        holidays: list[dict] = []
        assert is_rest_day(date(2026, 7, 15), holidays, weekly_work_days=5) is False

    def test_weekend_is_rest(self) -> None:
        """周末是休息日。"""
        holidays: list[dict] = []
        assert is_rest_day(date(2026, 7, 18), holidays, weekly_work_days=5) is True

    def test_holiday_is_rest(self, sample_holidays: list[dict]) -> None:
        """法定放假日是休息日。"""
        assert is_rest_day(date(2026, 1, 1), sample_holidays, weekly_work_days=5) is True

    def test_adjusted_workday_is_not_rest(self, sample_holidays: list[dict]) -> None:
        """调休补班日不是休息日。"""
        assert is_rest_day(date(2026, 1, 24), sample_holidays, weekly_work_days=5) is False


class TestGetPeriodRange:
    """get_period_range：本期区间（连续非工作日段之间）。"""

    def test_normal_week_returns_monday_to_friday(self) -> None:
        """普通工作周：本期是周一到周五（前后周末是非工作日段）。"""
        holidays: list[dict] = []
        # 2026-07-15 周三
        result = get_period_range(date(2026, 7, 15), holidays, weekly_work_days=5)
        assert result is not None
        start, end = result
        assert start == date(2026, 7, 13)  # 周一
        assert end == date(2026, 7, 17)  # 周五

    def test_rest_day_returns_none(self, sample_holidays: list[dict]) -> None:
        """休息日返回 None（今天是非工作日）。"""
        # 2026-01-01 元旦
        result = get_period_range(date(2026, 1, 1), sample_holidays, weekly_work_days=5)
        assert result is None

    def test_weekend_returns_none(self) -> None:
        """周末返回 None。"""
        holidays: list[dict] = []
        result = get_period_range(date(2026, 7, 18), holidays, weekly_work_days=5)
        assert result is None

    def test_period_with_holiday_in_middle(self, sample_holidays: list[dict]) -> None:
        """假期前的工作日，本期到假期前一天结束。"""
        # 2026-01-23 周五（春节假期 1/26 开始，所以本期是 1/19-1/23）
        result = get_period_range(date(2026, 1, 23), sample_holidays, weekly_work_days=5)
        assert result is not None
        start, end = result
        # 1/17-1/18 是周末，所以本期从 1/19 周一开始
        assert start == date(2026, 1, 19)
        # 1/24 是调休补班日（工作日），1/25 是周日（非工作日），所以 end 是 1/24
        assert end == date(2026, 1, 24)


class TestGetPreviousWorkday:
    """get_previous_workday：前一个工作日。"""

    def test_previous_day_is_workday(self) -> None:
        """前一天是工作日。"""
        holidays: list[dict] = []
        # 2026-07-16 周四，前一天是 7/15 周三
        result = get_previous_workday(date(2026, 7, 16), holidays, weekly_work_days=5)
        assert result == date(2026, 7, 15)

    def test_skip_weekend(self) -> None:
        """跳过周末（周一的前一个工作日是周五）。"""
        holidays: list[dict] = []
        # 2026-07-20 周一，前一个工作日是 7/17 周五
        result = get_previous_workday(date(2026, 7, 20), holidays, weekly_work_days=5)
        assert result == date(2026, 7, 17)

    def test_skip_holiday(self, sample_holidays: list[dict]) -> None:
        """跳过法定假日。"""
        # 2026-01-02 周五，前一天是 1/1 元旦（假日），前一个工作日是 12/31 周四
        result = get_previous_workday(date(2026, 1, 2), sample_holidays, weekly_work_days=5)
        assert result == date(2025, 12, 31)

    def test_include_adjusted_workday(self, sample_holidays: list[dict]) -> None:
        """调休补班日算工作日。"""
        # 2026-02-09 周一，前一个工作日是 2/8 周日（普通周末，非工作日），
        # 再往前 2/7 周六是调休补班日（工作日）
        result = get_previous_workday(date(2026, 2, 9), sample_holidays, weekly_work_days=5)
        assert result == date(2026, 2, 7)
