"""
test_record_service - 记录服务集成测试
========================================

覆盖 src/services/record_service.py 的 RecordService：
- mark_leave：请假标记
- manual_record：手动补录
- clear_record：删除记录
- check_yesterday / confirm_yesterday / skip_yesterday：次日确认流程
- should_check_yesterday / mark_yesterday_checked / reset_yesterday_flag：标志管理
- get_daily_worktime / get_date_range_worktime / get_all_holidays：查询

用 tmp_db 隔离数据库，monkeypatch 固定 datetime.now() 确保结果可复现。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.data.holiday_repo import HolidayRepository
from src.data.settings_repo import SettingsRepository
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.services.stats_service import StatsService

# 测试用的固定「当前时间」：2026-07-15 14:00:00 周三下午
_FIXED_NOW = datetime(2026, 7, 15, 14, 0, 0)


class _FixedDatetime(datetime):
    """datetime 子类，now() 返回固定时间，用于测试。"""

    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW


@pytest.fixture
def record_service(tmp_db, sample_holidays, monkeypatch) -> RecordService:
    """构造测试用 RecordService（含 StatsService 依赖）。"""
    # 固定 datetime.now()：stats_service 和 record_service 都用
    monkeypatch.setattr("src.services.stats_service.datetime", _FixedDatetime)
    monkeypatch.setattr("src.services.record_service.datetime", _FixedDatetime)

    settings_repo = SettingsRepository(db_path=str(tmp_db))
    settings_service = SettingsService(settings_repo)
    settings_service.init()

    holiday_repo = HolidayRepository(db_path=str(tmp_db))
    holiday_repo.save_year(2026, sample_holidays)

    worktime_repo = DailyWorktimeRepository(db_path=str(tmp_db))

    stats_service = StatsService(
        worktime_repo=worktime_repo,
        holiday_repo=holiday_repo,
        settings_service=settings_service,
    )
    return RecordService(
        worktime_repo=worktime_repo,
        holiday_repo=holiday_repo,
        settings_service=settings_service,
        stats_service=stats_service,
    )


def _insert_record(
    repo: DailyWorktimeRepository,
    work_date: date,
    start: datetime | None = None,
    end: datetime | None = None,
    total_hours: float | None = None,
    source: str = "auto",
    is_confirmed: int = 0,
) -> None:
    """辅助：插入一条工时记录。"""
    repo.upsert(
        work_date,
        start_time=start,
        end_time=end,
        total_hours=total_hours,
        required_hours=8.0,
        source=source,
        is_confirmed=is_confirmed,
    )


class TestMarkLeave:
    """mark_leave：请假标记。"""

    def test_mark_leave_writes_record(self, record_service: RecordService) -> None:
        """请假后写入 leave_type 和 note。"""
        leave_date = date(2026, 7, 20)
        record_service.mark_leave(leave_date, "annual")

        record = record_service.get_daily_worktime(leave_date)
        assert record is not None
        assert record["leave_type"] == "annual"
        assert "年假" in record["note"]

    def test_mark_leave_unknown_type(self, record_service: RecordService) -> None:
        """未知请假类型用原值。"""
        leave_date = date(2026, 7, 20)
        record_service.mark_leave(leave_date, "custom_type")

        record = record_service.get_daily_worktime(leave_date)
        assert record is not None
        assert record["leave_type"] == "custom_type"


class TestManualRecord:
    """manual_record：手动补录。"""

    def test_manual_record_same_day(self, record_service: RecordService) -> None:
        """同一天上下班，返回工时。"""
        work_dt = date(2026, 7, 13)
        total = record_service.manual_record(work_dt, "09:00", "17:30")

        assert total == pytest.approx(8.5, abs=0.01)
        record = record_service.get_daily_worktime(work_dt)
        assert record is not None
        assert record["source"] == "manual"
        assert record["is_confirmed"] == 1

    def test_manual_record_overnight(self, record_service: RecordService) -> None:
        """跨天补录（下班时间 < 上班时间 → 次日）。"""
        work_dt = date(2026, 7, 13)
        total = record_service.manual_record(work_dt, "22:00", "06:00")

        assert total == pytest.approx(8.0, abs=0.01)
        record = record_service.get_daily_worktime(work_dt)
        assert record is not None
        assert record["total_hours"] == 8.0

    def test_manual_record_invalid_format_raises(self, record_service: RecordService) -> None:
        """非法时间格式抛 ValueError。"""
        with pytest.raises(ValueError, match="时间格式不正确"):
            record_service.manual_record(date(2026, 7, 13), "abc", "17:00")


class TestClearRecord:
    """clear_record：删除记录。"""

    def test_clear_existing_record(self, record_service: RecordService) -> None:
        """删除已有记录。"""
        work_dt = date(2026, 7, 13)
        record_service.manual_record(work_dt, "09:00", "17:30")
        assert record_service.get_daily_worktime(work_dt) is not None

        record_service.clear_record("2026-07-13")
        assert record_service.get_daily_worktime(work_dt) is None

    def test_clear_nonexistent_no_error(self, record_service: RecordService) -> None:
        """删除不存在的记录不报错。"""
        record_service.clear_record("2026-12-31")  # 不抛异常即通过


class TestYesterdayConfirm:
    """次日确认流程。"""

    def test_should_check_yesterday_initial_true(self, record_service: RecordService) -> None:
        """初始状态需要检查。"""
        assert record_service.should_check_yesterday() is True

    def test_mark_yesterday_checked(self, record_service: RecordService) -> None:
        """标记后不再需要检查。"""
        record_service.mark_yesterday_checked()
        assert record_service.should_check_yesterday() is False

    def test_reset_yesterday_flag(self, record_service: RecordService) -> None:
        """重置标志后重新需要检查。"""
        record_service.mark_yesterday_checked()
        assert record_service.should_check_yesterday() is False

        record_service.reset_yesterday_flag()
        assert record_service.should_check_yesterday() is True

    def test_check_yesterday_no_previous(self, record_service: RecordService) -> None:
        """无前一工作日记录时返回 None。"""
        result = record_service.check_yesterday()
        assert result is None

    def test_check_yesterday_with_unconfirmed_record(self, record_service: RecordService) -> None:
        """前一工作日有未确认记录时返回 (prev, daily)。"""
        # 今天是 2026-07-15 周三，前一工作日是 2026-07-14 周二
        prev = date(2026, 7, 14)
        _insert_record(
            record_service._worktime_repo,
            prev,
            start=datetime(2026, 7, 14, 9, 0, 0),
            end=datetime(2026, 7, 14, 17, 30, 0),
            total_hours=8.5,
            is_confirmed=0,  # 未确认
        )

        result = record_service.check_yesterday()
        assert result is not None
        result_date, result_daily = result
        assert result_date == prev
        assert result_daily["start_time"] is not None

    def test_check_yesterday_with_confirmed_returns_none(
        self, record_service: RecordService
    ) -> None:
        """前一工作日已确认时返回 None。"""
        prev = date(2026, 7, 14)
        _insert_record(
            record_service._worktime_repo,
            prev,
            start=datetime(2026, 7, 14, 9, 0, 0),
            end=datetime(2026, 7, 14, 17, 30, 0),
            total_hours=8.5,
            is_confirmed=1,  # 已确认
        )

        result = record_service.check_yesterday()
        assert result is None

    def test_confirm_yesterday(self, record_service: RecordService) -> None:
        """确认前一天的下班时间。"""
        prev = date(2026, 7, 14)
        _insert_record(
            record_service._worktime_repo,
            prev,
            start=datetime(2026, 7, 14, 9, 0, 0),
            is_confirmed=0,
        )

        end_time = datetime(2026, 7, 14, 17, 30, 0)
        record_service.confirm_yesterday(prev, end_time)

        record = record_service.get_daily_worktime(prev)
        assert record is not None
        assert record["is_confirmed"] == 1
        assert record["total_hours"] == pytest.approx(8.5, abs=0.01)

    def test_confirm_yesterday_overnight(self, record_service: RecordService) -> None:
        """下班时间 < 上班时间时自动加一天。"""
        prev = date(2026, 7, 14)
        _insert_record(
            record_service._worktime_repo,
            prev,
            start=datetime(2026, 7, 14, 22, 0, 0),
            is_confirmed=0,
        )

        end_time = datetime(2026, 7, 15, 6, 0, 0)  # 次日 6 点
        record_service.confirm_yesterday(prev, end_time)

        record = record_service.get_daily_worktime(prev)
        assert record is not None
        assert record["is_confirmed"] == 1
        assert record["total_hours"] == pytest.approx(8.0, abs=0.01)

    def test_skip_yesterday(self, record_service: RecordService) -> None:
        """跳过次日确认（标记已确认但不改数据）。"""
        prev = date(2026, 7, 14)
        _insert_record(
            record_service._worktime_repo,
            prev,
            start=datetime(2026, 7, 14, 9, 0, 0),
            is_confirmed=0,
        )

        record_service.skip_yesterday(prev)

        record = record_service.get_daily_worktime(prev)
        assert record is not None
        assert record["is_confirmed"] == 1
        # start_time 保留不变
        assert record["start_time"] is not None


class TestQueries:
    """查询方法。"""

    def test_get_daily_worktime_nonexistent(self, record_service: RecordService) -> None:
        """查询不存在的日期返回 None。"""
        assert record_service.get_daily_worktime(date(2026, 12, 31)) is None

    def test_get_date_range_worktime(self, record_service: RecordService) -> None:
        """范围查询。"""
        _insert_record(
            record_service._worktime_repo,
            date(2026, 7, 13),
            start=datetime(2026, 7, 13, 9, 0, 0),
        )
        _insert_record(
            record_service._worktime_repo,
            date(2026, 7, 14),
            start=datetime(2026, 7, 14, 9, 0, 0),
        )

        records = record_service.get_date_range_worktime(date(2026, 7, 13), date(2026, 7, 14))
        assert len(records) == 2

    def test_get_all_holidays(self, record_service: RecordService) -> None:
        """获取全部节假日。"""
        holidays = record_service.get_all_holidays()
        # sample_holidays 含 11 条
        assert len(holidays) == 11
