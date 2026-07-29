"""
models - 数据模型
==================

定义业务层使用的数据 dataclass：
- 统计结果：WeekStats / PeriodStats / TodayStatus
- 数据库行：DailyWorktime / ActivityEvent / Holiday / Setting

数据库行仍以 dict 传递（向后兼容），但提供 dataclass 形式供新代码使用。
转换函数 dict_to_* 和 *_to_dict 在 Repository 层内部使用。

版本: 0.16.0
"""

from dataclasses import dataclass
from datetime import date, datetime

# ─── 统计结果 dataclass（计算层产出，向上传递给 UI）──────────────


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

    week_start: date | None = None
    week_end: date | None = None
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

    period_start: date | None = None
    period_end: date | None = None
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
    start_time: datetime | None = None
    end_time: datetime | None = None
    worked_hours: float = 0.0
    required_hours: float = 8.0
    is_target_reached: bool = False
    leave_type: str | None = None
    is_confirmed: int = 0
    has_anomaly: int = 0
    anomaly_note: str | None = None
    source: str | None = None


# ─── 数据库行 dataclass（对应 SQLite 表行）──────────────────────

# datetime 存入 SQLite 的统一格式串（与 database.py 的 DT_FORMAT 保持一致）
_DT_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class DailyWorktime:
    """
    每日工时记录（对应 daily_worktime 表一行）。

    Attributes:
        work_date:      工作日日期
        start_time:     上班时间（None=未上班）
        end_time:       下班时间（None=未下班）
        total_hours:    工时（小时，None=未计算）
        required_hours: 每日工时要求（小时）
        leave_type:     请假类型（annual/sick/personal/compensatory/None）
        is_confirmed:   是否已确认次日提醒（0/1）
        has_anomaly:    是否有异常（0/1）
        anomaly_note:   异常说明
        source:         数据来源（'auto'/'manual'）
        note:           备注
    """

    work_date: date
    start_time: datetime | None = None
    end_time: datetime | None = None
    total_hours: float | None = None
    required_hours: float | None = None
    leave_type: str | None = None
    is_confirmed: int = 0
    has_anomaly: int = 0
    anomaly_note: str | None = None
    source: str = "auto"
    note: str | None = None


@dataclass
class ActivityEvent:
    """
    键鼠活动事件（对应 activity_events 表一行）。

    Attributes:
        id:           自增主键
        timestamp:    轮询时刻
        idle_seconds: HIDIdleTime（秒）
        is_active:    是否有活动（idle < 5s）
        work_date:    归属工作日（6:00 窗口计算后）
        at_office:    是否在公司内网
    """

    id: int
    timestamp: datetime
    idle_seconds: float
    is_active: bool
    work_date: date
    at_office: bool = False


@dataclass
class Holiday:
    """
    节假日缓存记录（对应 holidays 表一行）。

    Attributes:
        date:       日期
        name:       节假日名称
        is_off_day: True=放假日, False=调休上班日
    """

    date: date
    name: str | None
    is_off_day: bool


@dataclass
class Setting:
    """
    设置键值对（对应 settings 表一行）。

    Attributes:
        key:   设置键名
        value: 设置值
    """

    key: str
    value: str


# ─── dict ↔ dataclass 转换函数（Repository 层内部使用）──────────


def dict_to_daily_worktime(d: dict) -> DailyWorktime:
    """dict → DailyWorktime dataclass。"""
    return DailyWorktime(
        work_date=date.fromisoformat(d["work_date"]),
        start_time=_parse_dt(d.get("start_time")),
        end_time=_parse_dt(d.get("end_time")),
        total_hours=_parse_float(d.get("total_hours")),
        required_hours=_parse_float(d.get("required_hours")),
        leave_type=d.get("leave_type"),
        is_confirmed=int(d.get("is_confirmed", 0)),
        has_anomaly=int(d.get("has_anomaly", 0)),
        anomaly_note=d.get("anomaly_note"),
        source=d.get("source", "auto"),
        note=d.get("note"),
    )


def dict_to_activity_event(d: dict) -> ActivityEvent:
    """dict → ActivityEvent dataclass。"""
    return ActivityEvent(
        id=int(d["id"]),
        timestamp=datetime.strptime(d["timestamp"], _DT_FORMAT),
        idle_seconds=float(d["idle_seconds"]),
        is_active=bool(d["is_active"]),
        work_date=date.fromisoformat(d["work_date"]),
        at_office=bool(d.get("at_office", 0)),
    )


def dict_to_holiday(d: dict) -> Holiday:
    """dict → Holiday dataclass。"""
    return Holiday(
        date=date.fromisoformat(d["date"]),
        name=d.get("name"),
        is_off_day=bool(d["is_off_day"]),
    )


def _parse_dt(s: str | None) -> datetime | None:
    """解析 datetime 字符串，None 或空返回 None。"""
    if not s:
        return None
    return datetime.strptime(s, _DT_FORMAT)


def _parse_float(v: float | int | str | None) -> float | None:
    """解析 float，None 返回 None。"""
    if v is None:
        return None
    return float(v)
