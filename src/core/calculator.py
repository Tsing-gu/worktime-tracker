# -*- coding: utf-8 -*-
"""
calculator - 工时计算
====================

工时计算类，构造期注入节假日、每日目标工时等配置，
方法签名精简为 (today, records, now) 三参。

版本: 0.8.0
"""

from datetime import datetime, date, timedelta
from typing import Optional, List

from src.data.models import WeekStats, MonthStats, TodayStatus, PeriodStats
from src.core.date_utils import (
    get_week_range, get_month_range, is_workday, is_rest_day,
    get_period_range, get_previous_workday,
)


class WorktimeCalculator:
    """工时计算器，封装本期/月/周/今日的工时统计逻辑。

    构造期注入配置参数，避免每次调用重复传五件套。

    Args:
        holidays:             节假日列表（dict 列表，含 date/is_off_day）
        daily_required:       每日工时要求（小时）
        holiday_auto_exclude: 是否自动排除周末
        weekly_work_days:     每周工作天数
    """

    def __init__(
        self,
        holidays: list,
        daily_required: float = 8.0,
        holiday_auto_exclude: bool = True,
        weekly_work_days: int = 5,
    ):
        self.holidays = holidays
        self.daily_required = daily_required
        self.holiday_auto_exclude = holiday_auto_exclude
        self.weekly_work_days = weekly_work_days

    def period_stats(self, today: date, records: list, now: datetime = None) -> PeriodStats:
        """计算本期工时统计。

        本期 = 两个连续非工作日段之间的工作日区间。
        """
        if now is None:
            now = datetime.now()

        period = get_period_range(today, self.holidays)
        if period is None:
            return PeriodStats(is_rest=True)

        period_start, period_end = period
        stats = self._iterate_range(period_start, period_end, today, records, now)
        return self._build_period_stats(period_start, period_end, stats, now)

    def month_stats(self, today: date, records: list, now: datetime = None) -> PeriodStats:
        """计算本月工时统计。"""
        if now is None:
            now = datetime.now()

        month_start, month_end = get_month_range(today)
        stats = self._iterate_range(month_start, month_end, today, records, now)
        return self._build_period_stats(month_start, month_end, stats, now)

    def week_stats(self, today: date, records: list, now: datetime = None) -> WeekStats:
        """计算本周工时统计。"""
        if now is None:
            now = datetime.now()

        week_start_date, week_end_date = get_week_range(today, self.weekly_work_days)

        total_workdays = 0
        worked_days = 0
        worked_hours = 0.0
        total_required_hours = 0.0
        today_required = self.daily_required

        d = week_start_date
        while d <= week_end_date:
            if d > today:
                break
            if is_workday(d, self.holidays, self.holiday_auto_exclude):
                rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
                if rec:
                    if rec.get("leave_type") and rec["leave_type"] != "none":
                        pass
                    else:
                        total_workdays += 1
                        rec_required = rec.get("required_hours")
                        if rec_required is not None:
                            total_required_hours += rec_required
                        else:
                            total_required_hours += self.daily_required
                        if d == today:
                            today_required = rec_required if rec_required is not None else self.daily_required
                        start_str = rec.get("start_time")
                        if start_str:
                            worked_days += 1
                            if rec.get("total_hours") is not None and rec.get("end_time"):
                                worked_hours += rec["total_hours"]
                            elif not rec.get("end_time"):
                                start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                                worked_hours += (now - start).total_seconds() / 3600.0
                else:
                    total_workdays += 1
                    total_required_hours += self.daily_required
            d += timedelta(days=1)

        remaining_days = max(0, total_workdays - worked_days)
        remaining_needed = max(0, total_required_hours - worked_hours)
        remaining_per_day = remaining_needed / remaining_days if remaining_days > 0 else 0
        progress = worked_hours / total_required_hours if total_required_hours > 0 else 0

        return WeekStats(
            week_start=week_start_date,
            week_end=week_end_date,
            total_workdays=total_workdays,
            worked_days=worked_days,
            worked_hours=round(worked_hours, 2),
            daily_required=today_required,
            remaining_days=remaining_days,
            remaining_needed=round(remaining_needed, 2),
            remaining_per_day=round(remaining_per_day, 2),
            progress=round(progress, 4),
        )

    def today_status(
        self,
        today: date,
        daily_record: Optional[dict],
        now: datetime = None,
    ) -> TodayStatus:
        """计算今日实时工时状态。"""
        if now is None:
            now = datetime.now()

        if not daily_record:
            return TodayStatus(required_hours=self.daily_required)

        start_str = daily_record.get("start_time")
        end_str = daily_record.get("end_time")
        start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S") if start_str else None
        end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S") if end_str else None

        if start_time and not end_time:
            worked_hours = (now - start_time).total_seconds() / 3600.0
        elif start_time and end_time:
            worked_hours = (end_time - start_time).total_seconds() / 3600.0
        else:
            worked_hours = 0

        record_required = daily_record.get("required_hours")
        effective_required = record_required if record_required is not None else self.daily_required

        return TodayStatus(
            has_started=start_time is not None,
            start_time=start_time,
            end_time=end_time,
            worked_hours=round(worked_hours, 2),
            required_hours=effective_required,
            is_target_reached=worked_hours >= effective_required,
            leave_type=daily_record.get("leave_type"),
            is_confirmed=daily_record.get("is_confirmed", 0),
            has_anomaly=daily_record.get("has_anomaly", 0),
            anomaly_note=daily_record.get("anomaly_note"),
            source=daily_record.get("source"),
        )

    def detect_anomalies(self, activities: list) -> Optional[str]:
        """检测活动记录中的异常情况。"""
        if not activities:
            return None

        for a in activities:
            if a["is_active"]:
                ts = datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M:%S")
                if ts.hour < 6:
                    return f"上班时间早于6:00（{ts.strftime('%H:%M')}）"

        active_count = sum(1 for a in activities if a["is_active"])
        if active_count > 100:
            return f"活动记录异常多（{active_count}条），可能存在采样异常"

        long_gaps = 0
        prev_active_ts = None
        for a in activities:
            ts = datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M:%S")
            if a["is_active"]:
                if prev_active_ts:
                    gap = (ts - prev_active_ts).total_seconds()
                    if gap > 7200:
                        long_gaps += 1
                prev_active_ts = ts

        if long_gaps >= 3:
            return f"一天内有{long_gaps}次超过2小时的活动断层"

        return None

    def previous_workday(self, today: date) -> Optional[date]:
        """获取前一个工作日。"""
        return get_previous_workday(today, self.holidays, self.holiday_auto_exclude)

    def _iterate_range(
        self,
        start: date,
        end: date,
        today: date,
        records: list,
        now: datetime,
    ) -> dict:
        """遍历日期区间，统计工作天数/已工作天数/已工作工时/今天之前工时。

        本期和月统计的共享逻辑，消除重复代码。

        Returns:
            dict: total_workdays, worked_days, worked_hours, hours_before_today,
                  remaining_days
        """
        total_workdays = 0
        worked_days = 0
        worked_hours = 0.0
        hours_before_today = 0.0

        d = start
        while d <= end:
            if is_workday(d, self.holidays, self.holiday_auto_exclude):
                rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
                is_leave = rec and rec.get("leave_type") and rec["leave_type"] != "none"
                if is_leave:
                    pass
                else:
                    total_workdays += 1
                    if d <= today:
                        if rec:
                            start_str = rec.get("start_time")
                            if start_str:
                                worked_days += 1
                                if rec.get("total_hours") is not None and rec.get("end_time"):
                                    h = rec["total_hours"]
                                elif not rec.get("end_time"):
                                    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                                    h = (now - start_dt).total_seconds() / 3600.0
                                else:
                                    h = 0
                                worked_hours += h
                                if d < today:
                                    hours_before_today += h
            d += timedelta(days=1)

        remaining_days = 0
        d = today
        while d <= end:
            if is_workday(d, self.holidays, self.holiday_auto_exclude):
                rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
                is_leave = rec and rec.get("leave_type") and rec["leave_type"] != "none"
                if not is_leave:
                    remaining_days += 1
            d += timedelta(days=1)

        return {
            "total_workdays": total_workdays,
            "worked_days": worked_days,
            "worked_hours": worked_hours,
            "hours_before_today": hours_before_today,
            "remaining_days": remaining_days,
        }

    def _build_period_stats(
        self,
        start: date,
        end: date,
        stats: dict,
        now: datetime,
    ) -> PeriodStats:
        """从遍历统计结果构建 PeriodStats 对象。"""
        target = stats["total_workdays"] * self.daily_required
        remaining_needed = max(0, target - stats["hours_before_today"])
        remaining_days = stats["remaining_days"]
        remaining_per_day = remaining_needed / remaining_days if remaining_days > 0 else 0
        worked_days = stats["worked_days"]
        daily_avg = stats["hours_before_today"] / (worked_days - 1) if worked_days > 1 else 0
        progress = stats["worked_hours"] / target if target > 0 else 0

        return PeriodStats(
            period_start=start,
            period_end=end,
            total_workdays=stats["total_workdays"],
            worked_days=worked_days,
            worked_hours=round(stats["worked_hours"], 2),
            daily_required=self.daily_required,
            daily_avg=round(daily_avg, 2),
            remaining_days=remaining_days,
            remaining_needed=round(remaining_needed, 2),
            remaining_per_day=round(remaining_per_day, 2),
            target_hours=round(target, 2),
            progress=round(progress, 4),
            is_rest=False,
        )
