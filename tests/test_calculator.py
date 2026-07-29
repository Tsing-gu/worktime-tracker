"""
test_calculator - 工时计算器单元测试
======================================

覆盖 src/core/calculator.py 的 WorktimeCalculatorCore，重点测试：
- today_status：今日实时状态（已上班/已下班/无记录）
- period_stats：本期统计（含休息日场景）
- month_stats：本月统计
- week_stats：本周统计
- detect_anomalies：异常检测

用 sample_holidays / sample_records fixture 构造典型场景。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.core.calculator import WorktimeCalculatorCore


@pytest.fixture
def calculator(sample_holidays: list[dict]) -> WorktimeCalculatorCore:
    """构造测试用计算器实例（daily_required=8.0, weekly_work_days=5）。"""
    return WorktimeCalculatorCore(
        holidays=sample_holidays,
        daily_required=8.0,
        holiday_auto_exclude=True,
        weekly_work_days=5,
    )


class TestTodayStatus:
    """today_status：今日实时状态。"""

    def test_no_record(self, calculator: WorktimeCalculatorCore, fixed_now: datetime) -> None:
        """无记录：has_started=False，worked_hours=0。"""
        today = date(2026, 7, 17)  # 周五，无记录
        status = calculator.today_status(today, None, now=fixed_now)
        assert status.has_started is False
        assert status.start_time is None
        assert status.worked_hours == 0.0
        assert status.required_hours == 8.0

    def test_working_no_end_time(self, calculator: WorktimeCalculatorCore) -> None:
        """工作中（无 end_time）：实时计算工时。"""
        # sample_records 里 2026-07-15 是工作中，start=09:30
        today = date(2026, 7, 15)
        record = {
            "start_time": "2026-07-15 09:30:00",
            "end_time": None,
            "total_hours": None,
            "required_hours": 8.0,
        }
        # now = 14:00，已工作 4.5h
        now = datetime(2026, 7, 15, 14, 0, 0)
        status = calculator.today_status(today, record, now=now)
        assert status.has_started is True
        assert status.start_time == datetime(2026, 7, 15, 9, 30, 0)
        assert status.end_time is None
        assert status.worked_hours == 4.5
        assert status.is_target_reached is False

    def test_off_work_with_end_time(self, calculator: WorktimeCalculatorCore) -> None:
        """已下班：用 total_hours 计算工时。"""
        # sample_records 里 2026-07-13 已下班，工时 8.5h
        today = date(2026, 7, 13)
        record = {
            "start_time": "2026-07-13 09:00:00",
            "end_time": "2026-07-13 17:30:00",
            "total_hours": 8.5,
            "required_hours": 8.0,
        }
        status = calculator.today_status(today, record)
        assert status.has_started is True
        assert status.start_time == datetime(2026, 7, 13, 9, 0, 0)
        assert status.end_time == datetime(2026, 7, 13, 17, 30, 0)
        assert status.worked_hours == 8.5
        assert status.is_target_reached is True

    def test_target_reached_threshold(self, calculator: WorktimeCalculatorCore) -> None:
        """达标阈值：worked_hours >= required_hours。"""
        today = date(2026, 7, 15)
        record = {
            "start_time": "2026-07-15 09:30:00",
            "end_time": None,
            "total_hours": None,
            "required_hours": 8.0,
        }
        # now = 17:30，已工作 8.0h，刚好达标
        now = datetime(2026, 7, 15, 17, 30, 0)
        status = calculator.today_status(today, record, now=now)
        assert status.worked_hours == 8.0
        assert status.is_target_reached is True

    def test_leave_record(self, calculator: WorktimeCalculatorCore) -> None:
        """请假记录：has_started=False（无 start_time）。"""
        today = date(2026, 7, 16)
        record = {
            "start_time": None,
            "end_time": None,
            "total_hours": None,
            "required_hours": 8.0,
            "leave_type": "annual",
        }
        status = calculator.today_status(today, record)
        assert status.has_started is False
        assert status.leave_type == "annual"


class TestPeriodStats:
    """period_stats：本期统计。"""

    def test_rest_day_returns_is_rest(
        self, calculator: WorktimeCalculatorCore, sample_holidays: list[dict]
    ) -> None:
        """休息日返回 is_rest=True。"""
        # 2026-01-01 元旦
        today = date(2026, 1, 1)
        stats = calculator.period_stats(today, [], now=datetime(2026, 1, 1, 12, 0, 0))
        assert stats.is_rest is True

    def test_weekend_returns_is_rest(self, calculator: WorktimeCalculatorCore) -> None:
        """周末返回 is_rest=True。"""
        # 2026-07-18 周六
        today = date(2026, 7, 18)
        stats = calculator.period_stats(today, [], now=datetime(2026, 7, 18, 12, 0, 0))
        assert stats.is_rest is True

    def test_normal_period_stats(
        self,
        calculator: WorktimeCalculatorCore,
        sample_records: list[dict],
    ) -> None:
        """正常本期统计：2026-07-15 周三，本期是 7/13-7/17。"""
        today = date(2026, 7, 15)
        now = datetime(2026, 7, 15, 14, 0, 0)
        stats = calculator.period_stats(today, sample_records, now=now)
        assert stats.is_rest is False
        assert stats.period_start == date(2026, 7, 13)
        assert stats.period_end == date(2026, 7, 17)
        # 本期 5 个工作日 - 1 请假（7/16）= 4（请假天不计入 total_workdays）
        assert stats.total_workdays == 4
        # 已工作天数：7/13（已下班）、7/14（已下班）、7/15（工作中）
        # 注意：7/16 请假不计入 worked_days
        assert stats.worked_days == 3
        assert stats.daily_required == 8.0


class TestMonthStats:
    """month_stats：本月统计。"""

    def test_july_2026_stats(
        self,
        calculator: WorktimeCalculatorCore,
        sample_records: list[dict],
    ) -> None:
        """2026年7月统计。"""
        today = date(2026, 7, 15)
        now = datetime(2026, 7, 15, 14, 0, 0)
        stats = calculator.month_stats(today, sample_records, now=now)
        assert stats.period_start == date(2026, 7, 1)
        assert stats.period_end == date(2026, 7, 31)
        # 2026年7月有 23 个工作日（weekday < 5），减 1 请假（7/16）= 22
        # 注意：calculator._iterate_range 把请假天排除出 total_workdays
        assert stats.total_workdays == 22
        assert stats.daily_required == 8.0


class TestWeekStats:
    """week_stats：本周统计。"""

    def test_normal_week(
        self,
        calculator: WorktimeCalculatorCore,
        sample_records: list[dict],
    ) -> None:
        """本周统计。

        注意：calculator.week_stats 调用 get_week_range(today, self.weekly_work_days)，
        传入的是 weekly_work_days（=5）而非 week_start（=1）。
        这是现有行为（可能是个 bug，但基线测试记录现状）：
        - get_week_range(today, 5) 用 5 作为 week_start，算出 week_start_offset
        - 2026-07-15 周三（weekday=2），delta = (2 - (5-1)) % 7 = -2 % 7 = 5
        - week_start = 7/15 - 5 = 7/10，week_end = 7/16
        """
        today = date(2026, 7, 15)
        now = datetime(2026, 7, 15, 14, 0, 0)
        stats = calculator.week_stats(today, sample_records, now=now)
        # 现有行为：get_week_range 用 weekly_work_days 当 week_start，算出 7/10-7/16
        assert stats.week_start == date(2026, 7, 10)
        assert stats.week_end == date(2026, 7, 16)
        # 该范围含 7/10-7/16，工作日 7/10(五) 7/13(一) 7/14(二) 7/15(三) 7/16(四请假)
        # total_workdays = 5 - 1(请假) = 4
        assert stats.total_workdays == 4
        assert stats.daily_required == 8.0


class TestDetectAnomalies:
    """detect_anomalies：异常检测。"""

    def test_empty_activities(self, calculator: WorktimeCalculatorCore) -> None:
        """空活动列表：无异常。"""
        assert calculator.detect_anomalies([]) is None

    def test_start_before_6am(self, calculator: WorktimeCalculatorCore) -> None:
        """上班早于 6:00 检测为异常。"""
        activities = [
            {"is_active": True, "timestamp": "2026-07-15 05:30:00"},
        ]
        result = calculator.detect_anomalies(activities)
        assert result is not None
        assert "6:00" in result

    def test_normal_activities_no_anomaly(self, calculator: WorktimeCalculatorCore) -> None:
        """正常活动记录无异常。"""
        activities = [
            {"is_active": True, "timestamp": "2026-07-15 09:00:00"},
            {"is_active": True, "timestamp": "2026-07-15 10:00:00"},
            {"is_active": True, "timestamp": "2026-07-15 11:00:00"},
        ]
        result = calculator.detect_anomalies(activities)
        assert result is None

    def test_too_many_activities(self, calculator: WorktimeCalculatorCore) -> None:
        """活动记录过多（>100 条）检测为异常。"""
        activities = [
            {"is_active": True, "timestamp": f"2026-07-15 {9 + i // 10}:{(i % 10) * 6:02d}:00"}
            for i in range(101)
        ]
        result = calculator.detect_anomalies(activities)
        assert result is not None
        assert "活动记录异常多" in result

    def test_long_gaps_anomaly(self, calculator: WorktimeCalculatorCore) -> None:
        """一天内有 3 次超过 2 小时的活动断层检测为异常。"""
        # 9:00, 12:00（gap 3h）, 15:00（gap 3h）, 18:00（gap 3h）→ 3 次 >2h 断层
        activities = [
            {"is_active": True, "timestamp": "2026-07-15 09:00:00"},
            {"is_active": True, "timestamp": "2026-07-15 12:00:00"},
            {"is_active": True, "timestamp": "2026-07-15 15:00:00"},
            {"is_active": True, "timestamp": "2026-07-15 18:00:00"},
        ]
        result = calculator.detect_anomalies(activities)
        assert result is not None
        assert "活动断层" in result
