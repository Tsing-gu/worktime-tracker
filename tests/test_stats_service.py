"""
test_stats_service - 统计服务集成测试
======================================

覆盖 src/services/stats_service.py 的 StatsService：
- get_today_status：今日实时工时状态
- get_required_hours：每日工时要求
- invalidate_calculator：计算器缓存失效
- get_period_stats / get_month_stats：本期 / 本月统计

用 tmp_db 隔离数据库，monkeypatch 固定 datetime.now() 确保结果可复现。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.data.holiday_repo import HolidayRepository
from src.data.settings_repo import SettingsRepository
from src.data.worktime_repo import DailyWorktimeRepository
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
def stats_service(tmp_db, sample_holidays, monkeypatch) -> StatsService:
    """构造测试用 StatsService（含已填充的 holiday / worktime / settings 仓储）。"""
    # 固定 datetime.now()
    monkeypatch.setattr("src.services.stats_service.datetime", _FixedDatetime)

    settings_repo = SettingsRepository(db_path=str(tmp_db))
    settings_service = SettingsService(settings_repo)
    settings_service.init()

    holiday_repo = HolidayRepository(db_path=str(tmp_db))
    # sample_holidays 全是 2026 年，按年写入
    holiday_repo.save_year(2026, sample_holidays)

    worktime_repo = DailyWorktimeRepository(db_path=str(tmp_db))
    return StatsService(
        worktime_repo=worktime_repo,
        holiday_repo=holiday_repo,
        settings_service=settings_service,
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


class TestGetTodayStatus:
    """get_today_status：今日实时工时状态。"""

    def test_no_record(self, stats_service: StatsService) -> None:
        """无记录时返回未上班状态。"""
        status = stats_service.get_today_status()
        assert status.has_started is False
        assert status.start_time is None
        assert status.worked_hours == 0.0

    def test_with_start_no_end(self, stats_service: StatsService) -> None:
        """有上班记录、无下班记录 → 实时计算工时。"""
        today = date(2026, 7, 15)
        start = datetime(2026, 7, 15, 9, 30, 0)
        _insert_record(stats_service._worktime_repo, today, start=start)

        status = stats_service.get_today_status()
        assert status.has_started is True
        assert status.start_time == start
        assert status.end_time is None
        # now=14:00，start=9:30，已工作 4.5h
        assert status.worked_hours == pytest.approx(4.5, abs=0.01)

    def test_with_start_and_end(self, stats_service: StatsService) -> None:
        """有上下班记录 → 按记录算工时。"""
        today = date(2026, 7, 15)
        start = datetime(2026, 7, 15, 9, 0, 0)
        end = datetime(2026, 7, 15, 17, 30, 0)
        _insert_record(stats_service._worktime_repo, today, start=start, end=end, total_hours=8.5)

        status = stats_service.get_today_status()
        assert status.has_started is True
        assert status.start_time == start
        assert status.end_time == end
        assert status.worked_hours == 8.5
        assert status.is_target_reached is True  # 8.5 >= 8.0


class TestGetRequiredHours:
    """get_required_hours：每日工时要求。"""

    def test_default_value(self, stats_service: StatsService) -> None:
        """默认值 8.0。"""
        assert stats_service.get_required_hours() == 8.0

    def test_after_update(self, stats_service: StatsService) -> None:
        """更新设置后读取新值。"""
        stats_service._settings.update(daily_required_hours=9.5)
        assert stats_service.get_required_hours() == 9.5


class TestInvalidateCalculator:
    """invalidate_calculator：计算器缓存失效。"""

    def test_cache_invalidation(self, stats_service: StatsService) -> None:
        """设置变更后计算器缓存失效，下次获取重新构建。"""
        calc1 = stats_service.get_calculator()
        calc2 = stats_service.get_calculator()
        assert calc1 is calc2  # 缓存命中

        stats_service.invalidate_calculator()
        calc3 = stats_service.get_calculator()
        assert calc3 is not calc1  # 缓存失效后重建

    def test_settings_change_triggers_invalidation(self, stats_service: StatsService) -> None:
        """SettingsService.update 触发 invalidate_calculator 回调。"""
        calc1 = stats_service.get_calculator()

        # update 会触发 register_on_changed 注册的回调
        stats_service._settings.update(daily_required_hours=9.0)

        calc2 = stats_service.get_calculator()
        assert calc2 is not calc1
        assert calc2.daily_required == 9.0


class TestGetPeriodStats:
    """get_period_stats：本期工时统计。"""

    def test_returns_period_stats(self, stats_service: StatsService) -> None:
        """返回 PeriodStats 实例。"""
        result = stats_service.get_period_stats()
        assert result is not None
        # 2026-07-15 周三，不是休息日
        assert result.is_rest is False
        assert result.daily_required == 8.0

    def test_rest_day_returns_is_rest(self, tmp_db, sample_holidays, monkeypatch) -> None:
        """休息日返回 is_rest=True。"""
        # 把今天设为周末（2026-07-18 周六）
        fixed_saturday = datetime(2026, 7, 18, 14, 0, 0)

        class _SatDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_saturday

        monkeypatch.setattr("src.services.stats_service.datetime", _SatDatetime)

        settings_repo = SettingsRepository(db_path=str(tmp_db))
        settings_service = SettingsService(settings_repo)
        settings_service.init()
        holiday_repo = HolidayRepository(db_path=str(tmp_db))
        worktime_repo = DailyWorktimeRepository(db_path=str(tmp_db))
        svc = StatsService(
            worktime_repo=worktime_repo,
            holiday_repo=holiday_repo,
            settings_service=settings_service,
        )
        result = svc.get_period_stats()
        assert result.is_rest is True


class TestGetMonthStats:
    """get_month_stats：本月工时统计。"""

    def test_returns_month_stats(self, stats_service: StatsService) -> None:
        """返回 PeriodStats 实例。"""
        # 插入几条本月记录
        repo = stats_service._worktime_repo
        _insert_record(
            repo,
            date(2026, 7, 13),
            start=datetime(2026, 7, 13, 9, 0, 0),
            end=datetime(2026, 7, 13, 17, 30, 0),
            total_hours=8.5,
            is_confirmed=1,
        )
        _insert_record(
            repo,
            date(2026, 7, 14),
            start=datetime(2026, 7, 14, 9, 0, 0),
            end=datetime(2026, 7, 14, 17, 0, 0),
            total_hours=8.0,
            is_confirmed=1,
        )

        result = stats_service.get_month_stats()
        assert result is not None
        assert result.is_rest is False
        assert result.daily_required == 8.0
