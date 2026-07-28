# -*- coding: utf-8 -*-
"""
models - 数据模型
==================

定义业务层使用的统计数据 dataclass。
数据库行仍以 dict 传递，此模块仅承载计算结果的传递。

版本: 0.8.0
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class WeekStats:
    """
    周工时统计数据。

    Attributes:
        week_start:          本周起始日
        week_end:            本周结束日
        total_workdays:      本周总工作日数（去除假日+请假+调休）
        worked_days:         已有下班记录的天数
        worked_hours:        已工作总时长（小时）
        daily_required:      每日工时要求（小时）
        remaining_days:      剩余工作日数
        remaining_needed:    剩余需达标总时长（小时）
        remaining_per_day:   剩余每天需达成时长（小时）
        progress:            进度比例 (0-1)
    """
    week_start: Optional[date] = None
    week_end: Optional[date] = None
    total_workdays: int = 0
    worked_days: int = 0
    worked_hours: float = 0.0
    daily_required: float = 8.0
    remaining_days: int = 0
    remaining_needed: float = 0.0
    remaining_per_day: float = 0.0
    progress: float = 0.0


@dataclass
class PeriodStats:
    """
    本期工时统计数据。

    本期 = 两个连续非工作日段之间的工作日区间。

    Attributes:
        period_start:        本期起始日
        period_end:          本期结束日
        total_workdays:      本期总工作天数（起点到终点，用于目标计算）
        worked_days:         已工作天数（有上班记录且非请假）
        worked_hours:        已工作总时长（小时）
        daily_required:      每日工时要求（小时）
        daily_avg:           日均工时（已工作工时 / 已工作天数）
        remaining_days:      剩余工作日数（今天之后到本期终点）
        remaining_needed:    剩余需达标总时长（小时）
        remaining_per_day:   剩余每天需达成时长（小时）
        target_hours:        目标总工时（总工作天数 × daily_required）
        progress:            进度比例 (0-1)
        is_rest:             今天是否为休息日（True=显示"休息中"）
    """
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    total_workdays: int = 0
    worked_days: int = 0
    worked_hours: float = 0.0
    daily_required: float = 8.0
    daily_avg: float = 0.0
    remaining_days: int = 0
    remaining_needed: float = 0.0
    remaining_per_day: float = 0.0
    target_hours: float = 0.0
    progress: float = 0.0
    is_rest: bool = False


@dataclass
class TodayStatus:
    """
    今日工时实时状态。

    每 30 秒轮询后更新，用于主界面实时展示。

    Attributes:
        has_started:       是否已上班
        start_time:        上班时间
        end_time:          下班时间（None=尚未下班）
        worked_hours:      当前已工作时长（小时）
        required_hours:    每日工时要求（小时）
        is_target_reached:  是否已达标
        leave_type:        请假类型
        is_confirmed:      是否已确认次日提醒
        has_anomaly:       是否有异常
        anomaly_note:      异常说明
        source:            数据来源
    """
    has_started: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    worked_hours: float = 0.0
    required_hours: float = 8.0
    is_target_reached: bool = False
    leave_type: Optional[str] = None
    is_confirmed: int = 0
    has_anomaly: int = 0
    anomaly_note: Optional[str] = None
    source: Optional[str] = None
