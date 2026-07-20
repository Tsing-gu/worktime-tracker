# -*- coding: utf-8 -*-
"""
models - 数据模型
==================

定义数据库行与业务对象之间的转换 dataclass。
所有层通过这些模型传递数据，避免直接操作原始 dict。

版本: 0.4.2
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class ActivityEvent:
    """
    键鼠活动事件记录。

    对应数据库 activity_events 表的一行。
    每次 30 秒轮询 HIDIdleTime 后生成一条记录。

    Attributes:
        id:            自增主键（数据库自动生成）
        timestamp:     轮询时刻
        idle_seconds:  HIDIdleTime 空闲时长（秒）
        is_active:     True=有活动(idle<5s), False=空闲(idle>5min)
        work_date:     归属工作日（6:00 窗口计算后的日期）
    """
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    idle_seconds: float = 0.0
    is_active: bool = False
    work_date: Optional[date] = None


@dataclass
class DailyWorktime:
    """
    每日工时记录。

    对应数据库 daily_worktime 表的一行。
    包含上下班时间、工时、请假、异常标记等完整信息。

    Attributes:
        work_date:            工作日日期
        start_time:           上班时间（datetime）
        end_time:             下班时间（datetime）
        total_hours:          每日工时（下班-上班，毛时间）
        required_hours:       每日工时要求
        is_holiday:           是否法定假日
        is_adjusted_workday:  是否调休上班日
        leave_type:           请假类型 (annual/sick/personal/compensatory/none)
        is_confirmed:         用户是否已确认次日提醒
        has_anomaly:          是否检测到异常
        anomaly_note:         异常说明文本
        source:               数据来源 'auto' | 'manual'
        note:                 备注
    """
    work_date: Optional[date] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_hours: Optional[float] = None
    required_hours: Optional[float] = None
    is_holiday: int = 0
    is_adjusted_workday: int = 0
    leave_type: Optional[str] = None
    is_confirmed: int = 0
    has_anomaly: int = 0
    anomaly_note: Optional[str] = None
    source: str = "auto"
    note: Optional[str] = None

    @classmethod
    def from_db_row(cls, row: dict) -> "DailyWorktime":
        """
        从数据库行 dict 构建 DailyWorktime 对象。

        Args:
            row: database.get_daily_worktime() 返回的 dict

        Returns:
            DailyWorktime 实例
        """
        def _parse_dt(val: str) -> Optional[datetime]:
            """将 'YYYY-MM-DD HH:MM:SS' 字符串解析为 datetime"""
            if not val:
                return None
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")

        def _parse_date(val: str) -> Optional[date]:
            """将 'YYYY-MM-DD' 字符串解析为 date"""
            if not val:
                return None
            return date.fromisoformat(val)

        return cls(
            work_date=_parse_date(row.get("work_date")),
            start_time=_parse_dt(row.get("start_time")),
            end_time=_parse_dt(row.get("end_time")),
            total_hours=row.get("total_hours"),
            required_hours=row.get("required_hours"),
            is_holiday=row.get("is_holiday", 0),
            is_adjusted_workday=row.get("is_adjusted_workday", 0),
            leave_type=row.get("leave_type"),
            is_confirmed=row.get("is_confirmed", 0),
            has_anomaly=row.get("has_anomaly", 0),
            anomaly_note=row.get("anomaly_note"),
            source=row.get("source", "auto"),
            note=row.get("note"),
        )


@dataclass
class Holiday:
    """
    节假日 / 调休日记录。

    对应数据库 holidays 表的一行。

    Attributes:
        date:       日期
        name:       节假日名称（如 "国庆节"）
        is_off_day: True=放假日, False=调休上班日
    """
    date: Optional[date] = None
    name: str = ""
    is_off_day: bool = False


@dataclass
class WeekStats:
    """
    周工时统计数据。

    由 calculator 计算后返回给 UI 层展示。

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
class MonthStats:
    """
    月工时统计数据。

    Attributes:
        month_start:     本月起始日
        month_end:       本月结束日
        worked_days:     已工作天数
        worked_hours:    已工作总时长（小时）
        avg_hours:       月均工时（小时/天）
        daily_required:  每日工时要求（小时）
        progress:        进度比例 (0-1)
    """
    month_start: Optional[date] = None
    month_end: Optional[date] = None
    worked_days: int = 0
    worked_hours: float = 0.0
    avg_hours: float = 0.0
    daily_required: float = 8.0
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
