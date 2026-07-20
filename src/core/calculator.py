# -*- coding: utf-8 -*-
"""
calculator - 工时计算（纯函数）
=================================

本模块全部为纯函数，不直接读写数据库。
所有函数接收数据参数（records / holidays），由调用方（service 层）从 DB 取数后传入。

核心功能:
    - get_week_stats():    周工时统计
    - get_month_stats():   月工时统计
    - get_today_status():  今日实时状态
    - detect_anomalies():  异常检测
    - get_previous_workday(): 获取上一个工作日

版本: 0.4.2
"""

from datetime import datetime, date, timedelta
from typing import Optional, List

from src.data.models import WeekStats, MonthStats, TodayStatus, PeriodStats


# ─── 日期工具 ─────────────────────────────────────────────────

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_week_range(dt: date, week_start: int = 1) -> tuple:
    """
    计算给定日期所在周的起止日期。

    Args:
        dt:         目标日期
        week_start: 周起始日（1=周一, 7=周日）

    Returns:
        (week_start_date, week_end_date) 两个 date
    """
    weekday = dt.weekday()
    days_since_start = (weekday - (week_start - 1)) % 7
    week_start_date = dt - timedelta(days=days_since_start)
    week_end_date = week_start_date + timedelta(days=6)
    return week_start_date, week_end_date


def get_month_range(dt: date) -> tuple:
    """
    计算给定日期所在月的起止日期。

    Args:
        dt: 目标日期

    Returns:
        (month_start, month_end) 两个 date
    """
    start = dt.replace(day=1)
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return start, end


# ─── 工作日判定 ──────────────────────────────────────────────

def is_workday(dt: date, holidays: list, holiday_auto_exclude: bool = True) -> bool:
    """
    判断某天是否为工作日。

    判定优先级:
        1. 节假日缓存表中有记录 → is_off_day=0 为调休上班日，is_off_day=1 为放假日
        2. 无节假日记录 → 按自然周（周一~周五为工作日），受 holiday_auto_exclude 开关控制

    Args:
        dt:                    目标日期
        holidays:              节假日列表（dict 列表，含 date/is_off_day）
        holiday_auto_exclude:  是否自动排除周末（True=周末非工作日）

    Returns:
        True=工作日, False=休息日
    """
    # 在节假日列表中查找
    dt_str = dt.isoformat()
    hol = next((h for h in holidays if h["date"] == dt_str), None)
    if hol:
        return not bool(hol["is_off_day"])

    # 无节假日记录 → 按自然周判断
    if holiday_auto_exclude:
        return dt.weekday() < 5

    return True


# ─── 本期工时统计（基于连续非工作日分段） ────────────────────

def is_rest_day(dt: date, holidays: list) -> bool:
    """
    判断某天是否为非工作日（休息日）。

    判定优先级:
        1. holidays 表中 is_off_day=1 → 放假日 → True
        2. holidays 表中 is_off_day=0 → 调休补班日 → False
        3. 无记录 → 周六日 → True

    Args:
        dt:        目标日期
        holidays:  节假日列表（dict 列表，含 date/is_off_day）

    Returns:
        True=非工作日, False=工作日
    """
    dt_str = dt.isoformat()
    hol = next((h for h in holidays if h["date"] == dt_str), None)
    if hol:
        return bool(hol["is_off_day"])
    return dt.weekday() >= 5


def _find_rest_segment_end_backward(dt: date, holidays: list, max_search: int = 365) -> Optional[date]:
    """
    从 dt 向前搜索，找到最近的连续非工作日段（≥2天）的最后一天。

    Args:
        dt:        搜索起点（不含）
        holidays:  节假日列表
        max_search: 最大向前搜索天数

    Returns:
        该段最后一个非工作日的 date，或 None（未找到）
    """
    d = dt - timedelta(days=1)
    for _ in range(max_search):
        if not is_rest_day(d, holidays):
            d -= timedelta(days=1)
            continue
        # d 是非工作日，向前延伸找到连续段的起始日
        seg_start = d
        while seg_start - timedelta(days=1) > d - timedelta(days=max_search) and is_rest_day(seg_start - timedelta(days=1), holidays):
            seg_start -= timedelta(days=1)
        # 段的起始日是 seg_start，最后一天是 d（因为 d 是从 dt 向前找到的第一个非工作日）
        if d >= seg_start + timedelta(days=1):
            return d
        # 只有1天的"段"不满足条件，继续向前搜索
        d = seg_start - timedelta(days=1)
    return None


def _find_rest_segment_start_forward(dt: date, holidays: list, max_search: int = 365) -> Optional[date]:
    """
    从 dt 向后搜索，找到最近的连续非工作日段（≥2天）的第一天。

    Args:
        dt:        搜索起点（不含）
        holidays:  节假日列表
        max_search: 最大向后搜索天数

    Returns:
        该段第一个非工作日的 date，或 None（未找到）
    """
    d = dt + timedelta(days=1)
    for _ in range(max_search):
        if not is_rest_day(d, holidays):
            d += timedelta(days=1)
            continue
        # d 是非工作日，向后延伸检查是否连续≥2天
        seg_end = d
        while seg_end + timedelta(days=1) < d + timedelta(days=max_search) and is_rest_day(seg_end + timedelta(days=1), holidays):
            seg_end += timedelta(days=1)
        if seg_end >= d + timedelta(days=1):
            return d
        # 只有1天，跳过
        d = seg_end + timedelta(days=1)
    return None


def get_period_range(today: date, holidays: list) -> Optional[tuple]:
    """
    计算给定日期所在"本期"的起止日期。

    本期 = 两个连续非工作日段（≥2天）之间的工作日区间。

    Args:
        today:    今天日期
        holidays: 节假日列表

    Returns:
        (period_start, period_end) 两个 date，或 None（今天是非工作日/休息中）
    """
    # 今天本身是非工作日 → 休息中
    if is_rest_day(today, holidays):
        return None

    # 向前找上一个连续非工作日段
    seg_end = _find_rest_segment_end_backward(today, holidays)
    if seg_end is not None:
        period_start = seg_end + timedelta(days=1)
    else:
        period_start = today.replace(month=1, day=1)

    # 向后找下一个连续非工作日段
    seg_start = _find_rest_segment_start_forward(today, holidays)
    if seg_start is not None:
        period_end = seg_start - timedelta(days=1)
    else:
        period_end = today.replace(month=12, day=31)

    return period_start, period_end


def get_period_stats(
    today: date,
    records: list,
    holidays: list,
    daily_required: float = 8.0,
    holiday_auto_exclude: bool = True,
    now: datetime = None,
) -> PeriodStats:
    """
    计算本期工时统计。

    本期 = 两个连续非工作日段之间的工作日区间。
    遍历本期区间，统计总工作天数、已工作天数、已工作时长等。

    Args:
        today:               今天日期
        records:             本期工时记录（dict 列表，来自 DB）
        holidays:            节假日列表
        daily_required:      每日工时要求（小时）
        holiday_auto_exclude: 是否自动排除周末
        now:                 当前时间（默认 datetime.now()，用于未下班实时计算）

    Returns:
        PeriodStats 对象
    """
    if now is None:
        now = datetime.now()

    period = get_period_range(today, holidays)
    if period is None:
        return PeriodStats(is_rest=True)

    period_start, period_end = period

    total_period_workdays = 0
    worked_days = 0
    worked_hours = 0.0
    hours_before_today = 0.0

    d = period_start
    while d <= period_end:
        if is_workday(d, holidays, holiday_auto_exclude):
            rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
            is_leave = rec and rec.get("leave_type") and rec["leave_type"] != "none"
            if is_leave:
                pass
            else:
                total_period_workdays += 1
                if d <= today:
                    if rec:
                        start_str = rec.get("start_time")
                        if start_str:
                            worked_days += 1
                            if rec.get("total_hours") is not None and rec.get("end_time"):
                                h = rec["total_hours"]
                            elif not rec.get("end_time"):
                                start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                                h = (now - start).total_seconds() / 3600.0
                            else:
                                h = 0
                            worked_hours += h
                            if d < today:
                                hours_before_today += h
        d += timedelta(days=1)

    # 剩余天数 = 今天到本期终点的工作日数（含今天，排除请假天）
    remaining_days = 0
    d = today
    while d <= period_end:
        if is_workday(d, holidays, holiday_auto_exclude):
            rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
            is_leave = rec and rec.get("leave_type") and rec["leave_type"] != "none"
            if not is_leave:
                remaining_days += 1
        d += timedelta(days=1)

    target = total_period_workdays * daily_required
    remaining_needed = max(0, target - hours_before_today)
    remaining_per_day = remaining_needed / remaining_days if remaining_days > 0 else 0
    daily_avg = hours_before_today / (worked_days - 1) if worked_days > 1 else 0
    progress = worked_hours / target if target > 0 else 0

    return PeriodStats(
        period_start=period_start,
        period_end=period_end,
        total_workdays=total_period_workdays,
        worked_days=worked_days,
        worked_hours=round(worked_hours, 2),
        daily_required=daily_required,
        daily_avg=round(daily_avg, 2),
        remaining_days=remaining_days,
        remaining_needed=round(remaining_needed, 2),
        remaining_per_day=round(remaining_per_day, 2),
        target_hours=round(target, 2),
        progress=round(progress, 4),
        is_rest=False,
    )

def get_week_stats(
    today: date,
    records: list,
    holidays: list,
    daily_required: float = 8.0,
    week_start: int = 1,
    holiday_auto_exclude: bool = True,
    now: datetime = None,
) -> WeekStats:
    """
    计算本周工时统计。

    遍历本周起始日到今天，统计:
        - 总工作日数（去除假日+请假，加上调休上班日）
        - 已工作天数（有上班记录的天数，含未下班）
        - 已工作总时长（已下班用固定值，未下班用实时计算）
        - 剩余天数及每天需达成时长

    Args:
        today:               今天日期
        records:             本周工时记录（dict 列表，来自 DB）
        holidays:            节假日列表
        daily_required:      每日工时要求（小时）
        week_start:          周起始日
        holiday_auto_exclude: 是否自动排除周末
        now:                 当前时间（默认 datetime.now()，用于未下班实时计算）

    Returns:
        WeekStats 对象
    """
    if now is None:
        now = datetime.now()

    week_start_date, week_end_date = get_week_range(today, week_start)

    total_workdays = 0
    worked_days = 0
    worked_hours = 0.0
    total_required_hours = 0.0  # 逐天从 DB 读 required_hours 累加
    today_required = daily_required  # 今天的目标值，用于 UI 显示

    # 遍历本周起始日到今天（未来的日子不计入）
    d = week_start_date
    while d <= week_end_date:
        if d > today:
            break
        if is_workday(d, holidays, holiday_auto_exclude):
            rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
            if rec:
                # 请假天不计入工作日数
                if rec.get("leave_type") and rec["leave_type"] != "none":
                    pass
                else:
                    total_workdays += 1
                    # 逐天读 required_hours，fallback 到参数
                    rec_required = rec.get("required_hours")
                    if rec_required is not None:
                        total_required_hours += rec_required
                    else:
                        total_required_hours += daily_required
                    # 记录今天的目标值
                    if d == today:
                        today_required = rec_required if rec_required is not None else daily_required
                    # 有上班记录即计入已工作天数
                    start_str = rec.get("start_time")
                    if start_str:
                        worked_days += 1
                        if rec.get("total_hours") is not None and rec.get("end_time"):
                            # 已下班 → 用固定值
                            worked_hours += rec["total_hours"]
                        elif not rec.get("end_time"):
                            # 未下班 → 实时计算
                            start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                            worked_hours += (now - start).total_seconds() / 3600.0
            else:
                total_workdays += 1
                total_required_hours += daily_required
        d += timedelta(days=1)

    # 剩余计算（按逐天累加的总目标计算）
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


# ─── 月工时统计 ──────────────────────────────────────────────

def get_month_stats(
    today: date,
    records: list,
    holidays: list,
    daily_required: float = 8.0,
    holiday_auto_exclude: bool = True,
    now: datetime = None,
) -> PeriodStats:
    """
    计算本月工时统计。

    遍历自然月1日到月末，按工作日口径统计（排除周六日和法定假期，含调休补班日）。
    请假天从总工作天数中扣除。格式与 get_period_stats() 一致。

    Args:
        today:               今天日期
        records:             本月工时记录
        holidays:            节假日列表
        daily_required:      每日工时要求（小时）
        holiday_auto_exclude: 是否自动排除周末
        now:                 当前时间（默认 datetime.now()，用于未下班实时计算）

    Returns:
        PeriodStats 对象
    """
    if now is None:
        now = datetime.now()

    month_start, month_end = get_month_range(today)

    total_workdays = 0
    worked_days = 0
    worked_hours = 0.0
    hours_before_today = 0.0

    d = month_start
    while d <= month_end:
        if is_workday(d, holidays, holiday_auto_exclude):
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
                                start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                                h = (now - start).total_seconds() / 3600.0
                            else:
                                h = 0
                            worked_hours += h
                            if d < today:
                                hours_before_today += h
        d += timedelta(days=1)

    # 剩余天数 = 今天到月末的工作日数（含今天，排除请假天）
    remaining_days = 0
    d = today
    while d <= month_end:
        if is_workday(d, holidays, holiday_auto_exclude):
            rec = next((r for r in records if r["work_date"] == d.isoformat()), None)
            is_leave = rec and rec.get("leave_type") and rec["leave_type"] != "none"
            if not is_leave:
                remaining_days += 1
        d += timedelta(days=1)

    target = total_workdays * daily_required
    remaining_needed = max(0, target - hours_before_today)
    remaining_per_day = remaining_needed / remaining_days if remaining_days > 0 else 0
    daily_avg = hours_before_today / (worked_days - 1) if worked_days > 1 else 0
    progress = worked_hours / target if target > 0 else 0

    return PeriodStats(
        period_start=month_start,
        period_end=month_end,
        total_workdays=total_workdays,
        worked_days=worked_days,
        worked_hours=round(worked_hours, 2),
        daily_required=daily_required,
        daily_avg=round(daily_avg, 2),
        remaining_days=remaining_days,
        remaining_needed=round(remaining_needed, 2),
        remaining_per_day=round(remaining_per_day, 2),
        target_hours=round(target, 2),
        progress=round(progress, 4),
        is_rest=False,
    )


# ─── 今日实时状态 ────────────────────────────────────────────

def get_today_status(
    today: date,
    daily_record: Optional[dict],
    daily_required: float = 8.0,
    now: datetime = None,
) -> TodayStatus:
    """
    计算今日实时工时状态。

    如果已下班，工时 = 下班 - 上班；
    如果未下班，工时 = 当前时间 - 上班（实时增长）。

    Args:
        today:          今天日期（保留兼容，暂未使用）
        daily_record:    今日工时记录 dict（来自 DB，可为 None）
        daily_required:  每日工时要求（小时）
        now:            当前时间（默认 datetime.now()，传入以便测试）

    Returns:
        TodayStatus 对象
    """
    if now is None:
        now = datetime.now()

    if not daily_record:
        return TodayStatus(
            required_hours=daily_required,
        )

    # 解析上下班时间
    start_str = daily_record.get("start_time")
    end_str = daily_record.get("end_time")
    start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S") if start_str else None
    end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S") if end_str else None

    # 计算已工作时长
    if start_time and not end_time:
        # 未下班 → 实时计算
        worked_hours = (now - start_time).total_seconds() / 3600.0
    elif start_time and end_time:
        # 已下班 → 固定值
        worked_hours = (end_time - start_time).total_seconds() / 3600.0
    else:
        worked_hours = 0

    # 优先使用记录中持久化的 required_hours（防止改设置后历史达标状态变化）
    # 如果记录中没有（NULL），则 fallback 到传入的 settings 实时值
    record_required = daily_record.get("required_hours")
    effective_required = record_required if record_required is not None else daily_required

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


# ─── 异常检测 ────────────────────────────────────────────────

def detect_anomalies(activities: list) -> Optional[str]:
    """
    检测活动记录中的异常情况。

    检测项:
        1. 上班时间早于 6:00
        2. 活动记录异常多（>100 条，可能采样异常）
        3. 一天内有 ≥3 次超过 2 小时的活动断层

    Args:
        activities: 活动记录列表（dict，含 timestamp/is_active）

    Returns:
        异常说明字符串，或 None 表示无异常
    """
    if not activities:
        return None

    # 检查是否有早于 6:00 的活动
    for a in activities:
        if a["is_active"]:
            ts = datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M:%S")
            if ts.hour < 6:
                return f"上班时间早于6:00（{ts.strftime('%H:%M')}）"

    # 活动记录过多
    active_count = sum(1 for a in activities if a["is_active"])
    if active_count > 100:
        return f"活动记录异常多（{active_count}条），可能存在采样异常"

    # 活动断层检测
    long_gaps = 0
    prev_active_ts = None
    for a in activities:
        ts = datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M:%S")
        if a["is_active"]:
            if prev_active_ts:
                gap = (ts - prev_active_ts).total_seconds()
                if gap > 7200:  # 超过 2 小时
                    long_gaps += 1
            prev_active_ts = ts

    if long_gaps >= 3:
        return f"一天内有{long_gaps}次超过2小时的活动断层"

    return None


# ─── 上一个工作日 ────────────────────────────────────────────

def get_previous_workday(
    today: date,
    holidays: list,
    holiday_auto_exclude: bool = True,
) -> Optional[date]:
    """
    获取指定日期之前的最近一个工作日。

    用于"次日确认提醒"功能：弹窗显示上一个工作日的下班时间。

    Args:
        today:               今天日期
        holidays:            节假日列表
        holiday_auto_exclude: 是否自动排除周末

    Returns:
        上一个工作日的 date，或 None（向前搜索 7 天无工作日）
    """
    d = today - timedelta(days=1)
    for _ in range(7):
        if is_workday(d, holidays, holiday_auto_exclude):
            return d
        d -= timedelta(days=1)
    return None
