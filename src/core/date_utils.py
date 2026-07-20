# -*- coding: utf-8 -*-
"""
date_utils - 纯日期计算工具
==========================

跨天归属、周/月范围、工作日判定等纯日期逻辑。
不依赖任何数据层，可被 core/services/ui 各层安全引用。

版本: 0.8.0
"""

from datetime import datetime, date, timedelta
from typing import Tuple, Optional, List


WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def compute_work_date(ts: datetime) -> date:
    """根据时间戳计算归属工作日。

    规则: 6:00 之前属于前一天的工作日窗口（前一天 6:00 ~ 今天 6:00）。

    Args:
        ts: 任意时刻

    Returns:
        归属工作日的 date 对象
    """
    if ts.hour < 6:
        return (ts - timedelta(days=1)).date()
    return ts.date()


def get_week_range(dt: date, week_start: int = 1) -> Tuple[date, date]:
    """获取 dt 所在周的范围（周一到周日）。

    Args:
        dt:         日期
        week_start: 周起始日（1=周一, 0=周日）

    Returns:
        (start, end) 元组
    """
    delta = (dt.weekday() - (week_start - 1)) % 7
    start = dt - timedelta(days=delta)
    end = start + timedelta(days=6)
    return start, end


def get_month_range(dt: date) -> Tuple[date, date]:
    """获取 dt 所在月的范围。

    Args:
        dt: 日期

    Returns:
        (月初, 月末) 元组
    """
    start = dt.replace(day=1)
    if dt.month == 12:
        end = dt.replace(day=31)
    else:
        end = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return start, end


def is_workday(dt: date, holidays: list, weekly_work_days: int = 5) -> bool:
    """判断指定日期是否为工作日。

    周末 + 非调休 → 非工作日
    节假日放假日 → 非工作日
    调休上班日 → 工作日

    Args:
        dt:               日期
        holidays:         节假日列表（dict 列表，含 date/is_off_day）
        weekly_work_days: 每周工作天数（默认 5）

    Returns:
        True=工作日, False=非工作日
    """
    holiday = _find_holiday(dt, holidays)
    if holiday:
        if holiday["is_off_day"] == 0:
            return True
        return False
    if weekly_work_days >= 7:
        return True
    if weekly_work_days <= 1:
        return dt.weekday() < weekly_work_days
    return dt.weekday() < weekly_work_days


def is_rest_day(dt: date, holidays: list, weekly_work_days: int = 5) -> bool:
    """判断指定日期是否为休息日（非工作日）。"""
    return not is_workday(dt, holidays, weekly_work_days)


def get_period_range(today: date, holidays: list, weekly_work_days: int = 5) -> Optional[Tuple[date, date]]:
    """获取本期范围（两个连续非工作日段之间的工作日区间）。

    从 today 向前和向后搜索，找到第一个非工作日作为边界。

    Args:
        today:            今日日期
        holidays:         节假日列表
        weekly_work_days: 每周工作天数（默认 5）

    Returns:
        (start, end) 元组，或 None（今天是非工作日）
    """
    if is_rest_day(today, holidays, weekly_work_days):
        return None

    start = today
    while start > today - timedelta(days=365):
        prev = start - timedelta(days=1)
        if is_rest_day(prev, holidays, weekly_work_days):
            break
        start = prev

    end = today
    while end < today + timedelta(days=365):
        nxt = end + timedelta(days=1)
        if is_rest_day(nxt, holidays, weekly_work_days):
            break
        end = nxt

    return start, end


def get_previous_workday(
    today: date, holidays: list, weekly_work_days: int = 5
) -> Optional[date]:
    """获取前一个工作日。

    Args:
        today:            今日日期
        holidays:         节假日列表
        weekly_work_days: 每周工作天数（默认 5）

    Returns:
        前一个工作日 date，或 None
    """
    dt = today - timedelta(days=1)
    for _ in range(30):
        if is_workday(dt, holidays, weekly_work_days):
            return dt
        dt -= timedelta(days=1)
    return None


def _find_holiday(dt: date, holidays: list) -> Optional[dict]:
    """从节假日列表中查找指定日期。"""
    dt_str = dt.isoformat()
    for h in holidays:
        if h["date"] == dt_str:
            return h
    return None
