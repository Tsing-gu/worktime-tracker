"""
test_tracking_service - 追踪服务集成测试
==========================================

覆盖 src/services/tracking_service.py 的 TrackingService：
- edit_start_time：修改上班时间（含时间下限对齐、非法格式）
- manual_off：手动下班流程
- resume_after_off：下班后恢复
- ensure_start：回溯上班时间
- init_work_date：初始化工作日

用 tmp_db 隔离数据库，monkeypatch 固定 datetime.now() 和系统调用。
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.core.tracker import WorkTrackerCore
from src.data.activity_repo import ActivityRepository
from src.data.database import DT_FORMAT
from src.data.holiday_repo import HolidayRepository
from src.data.settings_repo import SettingsRepository
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.holiday_service import HolidayService
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.services.stats_service import StatsService
from src.services.tracking_service import TrackingService

# 测试用的固定「当前时间」：2026-07-15 14:00:00 周三下午
_FIXED_NOW = datetime(2026, 7, 15, 14, 0, 0)


class _FixedDatetime(datetime):
    """datetime 子类，now() 返回固定时间，用于测试。"""

    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW


@pytest.fixture
def tracking_service(tmp_db, sample_holidays, monkeypatch) -> TrackingService:
    """构造测试用 TrackingService（含全部依赖）。"""
    # 固定 datetime.now()
    monkeypatch.setattr("src.services.tracking_service.datetime", _FixedDatetime)
    monkeypatch.setattr("src.services.stats_service.datetime", _FixedDatetime)
    monkeypatch.setattr("src.services.record_service.datetime", _FixedDatetime)

    settings_repo = SettingsRepository(db_path=str(tmp_db))
    settings_service = SettingsService(settings_repo)
    settings_service.init()

    holiday_repo = HolidayRepository(db_path=str(tmp_db))
    holiday_repo.save_year(2026, sample_holidays)

    worktime_repo = DailyWorktimeRepository(db_path=str(tmp_db))
    activity_repo = ActivityRepository(db_path=str(tmp_db))

    holiday_service = MagicMock(spec=HolidayService)

    stats_service = StatsService(
        worktime_repo=worktime_repo,
        holiday_repo=holiday_repo,
        settings_service=settings_service,
    )
    record_service = RecordService(
        worktime_repo=worktime_repo,
        holiday_repo=holiday_repo,
        settings_service=settings_service,
        stats_service=stats_service,
    )
    return TrackingService(
        tracker=WorkTrackerCore(),
        activity_repo=activity_repo,
        worktime_repo=worktime_repo,
        settings_service=settings_service,
        holiday_service=holiday_service,
        record_service=record_service,
    )


class TestEditStartTime:
    """edit_start_time：修改上班时间。"""

    def test_normal_time(self, tracking_service: TrackingService) -> None:
        """正常时间写入。"""
        new_start = tracking_service.edit_start_time("09:30")

        assert new_start == datetime(2026, 7, 15, 9, 30, 0)
        record = tracking_service._worktime_repo.get(date(2026, 7, 15))
        assert record is not None
        assert record["source"] == "manual"
        assert record["start_time"] == datetime(2026, 7, 15, 9, 30, 0).strftime(DT_FORMAT)

    def test_before_work_start_floor(self, tracking_service: TrackingService) -> None:
        """早于 work_start_floor（06:00）→ 对齐到 06:00。"""
        new_start = tracking_service.edit_start_time("05:00")

        assert new_start == datetime(2026, 7, 15, 6, 0, 0)

    def test_at_work_start_floor(self, tracking_service: TrackingService) -> None:
        """恰好等于 work_start_floor（06:00）→ 原样写入。"""
        new_start = tracking_service.edit_start_time("06:00")

        assert new_start == datetime(2026, 7, 15, 6, 0, 0)

    def test_invalid_format_raises(self, tracking_service: TrackingService) -> None:
        """非法格式抛 ValueError。"""
        with pytest.raises(ValueError, match="请输入 HH:MM 格式"):
            tracking_service.edit_start_time("abc")

    def test_missing_minute_raises(self, tracking_service: TrackingService) -> None:
        """缺少分钟部分抛 ValueError。"""
        with pytest.raises(ValueError, match="请输入 HH:MM 格式"):
            tracking_service.edit_start_time("09")


class TestManualOff:
    """manual_off：手动下班。"""

    def test_no_start_returns_no_start(self, tracking_service: TrackingService) -> None:
        """无上班记录时返回 no_start 事件。"""
        result = tracking_service.manual_off()
        assert result.event == "no_start"

    def test_with_start_records_off_time(self, tracking_service: TrackingService) -> None:
        """有上班记录时写入下班时间。"""
        # 先插入上班记录
        today = date(2026, 7, 15)
        tracking_service._worktime_repo.upsert(
            today,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            source="auto",
            required_hours=8.0,
        )

        result = tracking_service.manual_off()
        assert result.event == "manual_off"
        assert result.off_time is not None

        record = tracking_service._worktime_repo.get(today)
        assert record is not None
        assert record["source"] == "manual"
        assert record["is_confirmed"] == 1
        assert record["end_time"] is not None


class TestResumeAfterOff:
    """resume_after_off：下班后恢复。"""

    def test_resume_clears_end_time(self, tracking_service: TrackingService) -> None:
        """恢复后清除下班时间。"""
        today = date(2026, 7, 15)
        # 插入一条已下班的记录
        tracking_service._worktime_repo.upsert(
            today,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            end_time=datetime(2026, 7, 15, 12, 0, 0),
            total_hours=3.0,
            source="auto",
            required_hours=8.0,
        )

        tracking_service.resume_after_off()

        record = tracking_service._worktime_repo.get(today)
        assert record is not None
        assert record.get("end_time") is None


class TestInitWorkDate:
    """init_work_date：初始化工作日。"""

    def test_init_sets_current_work_date(
        self, tracking_service: TrackingService, monkeypatch
    ) -> None:
        """init_work_date 设置 current_work_date。"""
        # Mock get_network_status 避免 network 调用
        monkeypatch.setattr(
            "src.services.tracking_service.get_network_status",
            lambda domain: {"at_office": False},
        )

        tracking_service.init_work_date()

        assert tracking_service.current_work_date == date(2026, 7, 15)
