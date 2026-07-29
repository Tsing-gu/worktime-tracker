"""
test_models - 数据模型 dataclass 单元测试
============================================

覆盖 src/data/models.py 的 dict ↔ dataclass 转换函数：
- dict_to_daily_worktime
- dict_to_activity_event
- dict_to_holiday
"""

from __future__ import annotations

from datetime import date, datetime

from src.data.models import (
    ActivityEvent,
    DailyWorktime,
    Holiday,
    Setting,
    dict_to_activity_event,
    dict_to_daily_worktime,
    dict_to_holiday,
)


class TestDictToDailyWorktime:
    """dict_to_daily_worktime：dict → DailyWorktime 转换。"""

    def test_full_record(self) -> None:
        """完整记录转换。"""
        d = {
            "work_date": "2026-07-15",
            "start_time": "2026-07-15 09:00:00",
            "end_time": "2026-07-15 17:30:00",
            "total_hours": 8.5,
            "required_hours": 8.0,
            "leave_type": None,
            "is_confirmed": 1,
            "has_anomaly": 0,
            "anomaly_note": None,
            "source": "auto",
            "note": None,
        }
        result = dict_to_daily_worktime(d)
        assert isinstance(result, DailyWorktime)
        assert result.work_date == date(2026, 7, 15)
        assert result.start_time == datetime(2026, 7, 15, 9, 0, 0)
        assert result.end_time == datetime(2026, 7, 15, 17, 30, 0)
        assert result.total_hours == 8.5
        assert result.required_hours == 8.0
        assert result.leave_type is None
        assert result.is_confirmed == 1
        assert result.has_anomaly == 0
        assert result.source == "auto"
        assert result.note is None

    def test_minimal_record(self) -> None:
        """最小记录（只有 work_date，其他字段缺失）。"""
        d = {"work_date": "2026-07-15"}
        result = dict_to_daily_worktime(d)
        assert result.work_date == date(2026, 7, 15)
        assert result.start_time is None
        assert result.end_time is None
        assert result.total_hours is None
        assert result.required_hours is None
        assert result.is_confirmed == 0
        assert result.has_anomaly == 0
        assert result.source == "auto"  # 默认值

    def test_leave_record(self) -> None:
        """请假记录转换。"""
        d = {
            "work_date": "2026-07-16",
            "start_time": None,
            "end_time": None,
            "total_hours": None,
            "required_hours": 8.0,
            "leave_type": "annual",
            "is_confirmed": 1,
            "has_anomaly": 0,
            "anomaly_note": None,
            "source": "auto",
            "note": "请假-年假",
        }
        result = dict_to_daily_worktime(d)
        assert result.start_time is None
        assert result.leave_type == "annual"
        assert result.note == "请假-年假"


class TestDictToActivityEvent:
    """dict_to_activity_event：dict → ActivityEvent 转换。"""

    def test_active_event(self) -> None:
        """活跃事件转换。"""
        d = {
            "id": 1,
            "timestamp": "2026-07-15 09:30:00",
            "idle_seconds": 2.5,
            "is_active": 1,
            "work_date": "2026-07-15",
            "at_office": 1,
        }
        result = dict_to_activity_event(d)
        assert isinstance(result, ActivityEvent)
        assert result.id == 1
        assert result.timestamp == datetime(2026, 7, 15, 9, 30, 0)
        assert result.idle_seconds == 2.5
        assert result.is_active is True
        assert result.work_date == date(2026, 7, 15)
        assert result.at_office is True

    def test_idle_event(self) -> None:
        """空闲事件转换。"""
        d = {
            "id": 2,
            "timestamp": "2026-07-15 12:00:00",
            "idle_seconds": 1800.0,
            "is_active": 0,
            "work_date": "2026-07-15",
            "at_office": 0,
        }
        result = dict_to_activity_event(d)
        assert result.is_active is False
        assert result.at_office is False

    def test_missing_at_office_defaults_false(self) -> None:
        """缺少 at_office 字段时默认 False。"""
        d = {
            "id": 3,
            "timestamp": "2026-07-15 14:00:00",
            "idle_seconds": 1.0,
            "is_active": 1,
            "work_date": "2026-07-15",
        }
        result = dict_to_activity_event(d)
        assert result.at_office is False


class TestDictToHoliday:
    """dict_to_holiday：dict → Holiday 转换。"""

    def test_off_day(self) -> None:
        """放假日转换。"""
        d = {"date": "2026-01-01", "name": "元旦", "is_off_day": 1}
        result = dict_to_holiday(d)
        assert isinstance(result, Holiday)
        assert result.date == date(2026, 1, 1)
        assert result.name == "元旦"
        assert result.is_off_day is True

    def test_adjusted_workday(self) -> None:
        """调休补班日转换。"""
        d = {"date": "2026-01-24", "name": "春节调休", "is_off_day": 0}
        result = dict_to_holiday(d)
        assert result.is_off_day is False

    def test_no_name(self) -> None:
        """无名称的节假日。"""
        d = {"date": "2026-01-01", "name": None, "is_off_day": 1}
        result = dict_to_holiday(d)
        assert result.name is None


class TestSettingDataclass:
    """Setting dataclass 基本测试。"""

    def test_create_setting(self) -> None:
        """创建 Setting 实例。"""
        s = Setting(key="daily_required_hours", value="8.0")
        assert s.key == "daily_required_hours"
        assert s.value == "8.0"
