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


class TestBackfillOffTime:
    """_backfill_off_time：跨天补录前一天未记录的下班时间。

    修复漏洞：原实现用 ``now - idle`` 推算下班时间，关机场景下
    HIDIdleTime 重置为 0 会得到错误时间。改为查询 activity_events 表。
    测试通过直接调用 _backfill_off_time（私有方法但测试可访问），
    构造前一天的 activity_events + worktime 记录验证各场景。
    """

    @staticmethod
    def _insert_prev_day(
        svc: TrackingService,
        prev_date: date,
        start_time: datetime,
        active_events: list[tuple[datetime, float, bool, bool]],
        source: str = "auto",
        end_time: datetime | None = None,
    ) -> None:
        """构造前一天的 worktime + activity_events 记录。

        Args:
            svc:              TrackingService 实例
            prev_date:        前一天日期
            start_time:       上班时间
            active_events:    活动事件列表 [(timestamp, idle, is_active, at_office), ...]
            source:           记录来源 auto/manual
            end_time:         已有下班时间（None 表示未下班）
        """
        svc._worktime_repo.upsert(
            prev_date,
            start_time=start_time,
            end_time=end_time,
            total_hours=(
                None if end_time is None else (end_time - start_time).total_seconds() / 3600.0
            ),
            source=source,
            required_hours=8.0,
        )
        for ts, idle, is_active, at_office in active_events:
            svc._activity_repo.record(ts, idle, is_active, at_office=at_office)

    def test_shutdown_scenario(self, tracking_service: TrackingService) -> None:
        """关机场景：前一天最后 active 22:00，次日 08:00 检测到跨天。

        修复前：now - idle = 08:00 - 3s ≈ 07:59（今天），对齐到 19:00，
                写入 end_time=今天 19:00，total_hours=34h（错误）。
        修复后：查询 activity_events 得 22:00（前一天），22:00 已超过 19:00 不对齐，
                写入 end_time=前一天 22:00，total_hours=13h（正确）。
        """
        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        # 模拟关机：最后活跃 22:00，22:30 轮询记录空闲（active=False）后关机
        events = [
            (datetime(2026, 7, 14, 9, 30, 0), 1.0, True, True),
            (datetime(2026, 7, 14, 22, 0, 0), 1.0, True, True),  # 最后活跃
            (datetime(2026, 7, 14, 22, 30, 0), 1800.0, False, True),  # 空闲
        ]
        self._insert_prev_day(tracking_service, prev_date, start_time, events)

        # 次日早上触发补录
        now = datetime(2026, 7, 15, 8, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        assert record["end_time"] is not None
        # off_time=22:00 已超过 floor 19:00，不对齐，保持 22:00
        assert record["end_time"] == datetime(2026, 7, 14, 22, 0, 0).strftime(DT_FORMAT)
        # total_hours = 22:00 - 09:00 = 13h
        assert record["total_hours"] == 13.0

    def test_sleep_scenario(self, tracking_service: TrackingService) -> None:
        """睡眠场景：前一天最后 active 23:30，次日 07:00 检测到跨天。"""
        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        events = [
            (datetime(2026, 7, 14, 23, 30, 0), 1.0, True, True),  # 最后活跃 23:30
        ]
        self._insert_prev_day(tracking_service, prev_date, start_time, events)

        now = datetime(2026, 7, 15, 7, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        # 23:30 已超过 19:00，不对齐，保持 23:30
        assert record["end_time"] == datetime(2026, 7, 14, 23, 30, 0).strftime(DT_FORMAT)
        assert record["total_hours"] == 14.5

    def test_aligns_to_floor(self, tracking_service: TrackingService) -> None:
        """最后 active 18:00（早于 floor 19:00）→ 对齐到 19:00。"""
        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        events = [
            (datetime(2026, 7, 14, 18, 0, 0), 1.0, True, True),  # 最后活跃 18:00
        ]
        self._insert_prev_day(tracking_service, prev_date, start_time, events)

        now = datetime(2026, 7, 15, 7, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        assert record["end_time"] == datetime(2026, 7, 14, 19, 0, 0).strftime(DT_FORMAT)
        assert record["total_hours"] == 10.0

    def test_skips_manual(self, tracking_service: TrackingService) -> None:
        """手动记录不补录。"""
        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        events = [
            (datetime(2026, 7, 14, 22, 0, 0), 1.0, True, True),
        ]
        self._insert_prev_day(tracking_service, prev_date, start_time, events, source="manual")

        now = datetime(2026, 7, 15, 7, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        # 手动记录不被覆盖
        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        assert record["source"] == "manual"
        assert record["end_time"] is None

    def test_skips_already_has_end(self, tracking_service: TrackingService) -> None:
        """已有下班记录不补录。"""
        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        existing_end = datetime(2026, 7, 14, 17, 0, 0)
        events = [
            (datetime(2026, 7, 14, 22, 0, 0), 1.0, True, True),
        ]
        self._insert_prev_day(
            tracking_service, prev_date, start_time, events, end_time=existing_end
        )

        now = datetime(2026, 7, 15, 7, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        # 已有下班记录不被覆盖
        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        assert record["end_time"] == existing_end.strftime(DT_FORMAT)

    def test_only_office_mode(self, tracking_service: TrackingService, monkeypatch) -> None:
        """only_office_time=True 用 get_last_active_at_office 查询。"""
        # 启用网络门控
        tracking_service._settings.update(only_office_time=True)

        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        # 最后在公司 17:00，之后 22:00 在家办公
        events = [
            (datetime(2026, 7, 14, 9, 30, 0), 1.0, True, True),
            (datetime(2026, 7, 14, 17, 0, 0), 1.0, True, True),  # 最后在公司
            (datetime(2026, 7, 14, 22, 0, 0), 1.0, True, False),  # 在家办公（不算）
        ]
        self._insert_prev_day(tracking_service, prev_date, start_time, events)

        now = datetime(2026, 7, 15, 7, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        # off_time=17:00 对齐到 19:00
        assert record["end_time"] == datetime(2026, 7, 14, 19, 0, 0).strftime(DT_FORMAT)
        assert record["total_hours"] == 10.0

    def test_no_active_events(self, tracking_service: TrackingService) -> None:
        """无 active 记录（全是空闲）→ 不补录。"""
        prev_date = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        events = [
            (datetime(2026, 7, 14, 22, 30, 0), 1800.0, False, True),  # 只有空闲
        ]
        self._insert_prev_day(tracking_service, prev_date, start_time, events)

        now = datetime(2026, 7, 15, 7, 0, 0)
        tracking_service._backfill_off_time(prev_date, now)

        record = tracking_service._worktime_repo.get(prev_date)
        assert record is not None
        assert record["end_time"] is None


class TestGetRecentPmsetSummary:
    """get_recent_pmset_summary：读取近 N 天 pmset 推断 + DB 对比。"""

    def test_returns_descending_by_date(
        self, tracking_service: TrackingService, monkeypatch
    ) -> None:
        """返回列表按日期降序（今天在最前）。"""

        # mock get_active_periods_from_pmset 返回固定值
        def fake_pmset(work_date, floor):
            return (datetime(2026, 7, 15, 9, 0), datetime(2026, 7, 15, 18, 0))

        monkeypatch.setattr(
            "src.services.tracking_service.get_active_periods_from_pmset", fake_pmset
        )

        summaries = tracking_service.get_recent_pmset_summary(days=7)

        assert len(summaries) == 7
        # 降序：今天 2026-07-15 在最前
        assert summaries[0].work_date == date(2026, 7, 15)
        assert summaries[-1].work_date == date(2026, 7, 9)
        # 推断时间正确
        assert summaries[0].first_active == datetime(2026, 7, 15, 9, 0)
        assert summaries[0].last_active == datetime(2026, 7, 15, 18, 0)

    def test_reflects_db_state(self, tracking_service: TrackingService, monkeypatch) -> None:
        """DB 已有记录时 has_start_record / has_end_record / source 正确反映。"""
        monkeypatch.setattr(
            "src.services.tracking_service.get_active_periods_from_pmset",
            lambda wd, floor: (None, None),
        )
        # 插一条已有上班记录（auto 来源）
        today = date(2026, 7, 15)
        tracking_service._worktime_repo.upsert(
            today,
            start_time=datetime(2026, 7, 15, 9, 30, 0),
            source="auto",
            required_hours=8.0,
        )

        summaries = tracking_service.get_recent_pmset_summary(days=3)

        # 今天有上班记录
        today_summary = summaries[0]
        assert today_summary.work_date == today
        assert today_summary.has_start_record is True
        assert today_summary.has_end_record is False
        assert today_summary.source == "auto"
        # 前两天无记录
        assert summaries[1].has_start_record is False
        assert summaries[2].has_start_record is False

    def test_days_param_controls_range(
        self, tracking_service: TrackingService, monkeypatch
    ) -> None:
        """days 参数控制读取天数。"""
        monkeypatch.setattr(
            "src.services.tracking_service.get_active_periods_from_pmset",
            lambda wd, floor: (None, None),
        )
        summaries = tracking_service.get_recent_pmset_summary(days=3)
        assert len(summaries) == 3

    def test_reflects_leave_record(self, tracking_service: TrackingService, monkeypatch) -> None:
        """DB 有请假记录时 leave_type 正确反映。"""
        monkeypatch.setattr(
            "src.services.tracking_service.get_active_periods_from_pmset",
            lambda wd, floor: (None, None),
        )
        today = date(2026, 7, 15)
        tracking_service._worktime_repo.upsert(today, leave_type="annual")

        summaries = tracking_service.get_recent_pmset_summary(days=1)
        assert summaries[0].leave_type == "annual"


class TestApplyPmsetStartTime:
    """apply_pmset_start_time：应用 pmset 推断上班时间到 DB。"""

    def test_applies_when_no_record(self, tracking_service: TrackingService) -> None:
        """无任何记录 → 应用成功。"""
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 15, 0)

        result = tracking_service.apply_pmset_start_time(target, start_time)

        assert result is True
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record["start_time"] == start_time.strftime(DT_FORMAT)
        assert record["source"] == "auto"
        assert record["required_hours"] == 8.0

    def test_skips_when_manual_record_exists(self, tracking_service: TrackingService) -> None:
        """已有手动记录 → 不覆盖。"""
        target = date(2026, 7, 14)
        existing_start = datetime(2026, 7, 14, 10, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=existing_start, source="manual", required_hours=8.0
        )

        result = tracking_service.apply_pmset_start_time(target, datetime(2026, 7, 14, 9, 15, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record["start_time"] == existing_start.strftime(DT_FORMAT)
        assert record["source"] == "manual"

    def test_skips_when_leave_record_exists(self, tracking_service: TrackingService) -> None:
        """已有请假记录 → 不覆盖。"""
        target = date(2026, 7, 14)
        tracking_service._worktime_repo.upsert(target, leave_type="sick")

        result = tracking_service.apply_pmset_start_time(target, datetime(2026, 7, 14, 9, 15, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record.get("leave_type") == "sick"
        assert record.get("start_time") is None

    def test_skips_when_auto_start_already_exists(self, tracking_service: TrackingService) -> None:
        """已有 auto 来源的上班记录 → 不覆盖（避免重复写入）。"""
        target = date(2026, 7, 14)
        existing_start = datetime(2026, 7, 14, 9, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=existing_start, source="auto", required_hours=8.0
        )

        result = tracking_service.apply_pmset_start_time(target, datetime(2026, 7, 14, 9, 15, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record["start_time"] == existing_start.strftime(DT_FORMAT)


class TestApplyPmsetEndTime:
    """apply_pmset_end_time：应用 pmset 推断下班时间到 DB。"""

    def test_applies_when_start_exists_no_end(self, tracking_service: TrackingService) -> None:
        """有上班记录、无下班 → 应用成功。

        推断下班 18:30 < off_time_floor 19:00 → 对齐到 19:00，
        total_hours = 19:00 - 09:00 = 10h。
        """
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=start_time, source="auto", required_hours=8.0
        )

        end_time = datetime(2026, 7, 14, 18, 30, 0)
        result = tracking_service.apply_pmset_end_time(target, end_time)

        assert result is True
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        # 18:30 对齐到 19:00
        assert record["end_time"] == datetime(2026, 7, 14, 19, 0, 0).strftime(DT_FORMAT)
        assert record["total_hours"] == 10.0
        assert record["source"] == "auto"
        assert record["is_confirmed"] == 0

    def test_applies_late_end_time_no_align(self, tracking_service: TrackingService) -> None:
        """推断下班晚于 off_time_floor → 不对齐，原样写入。

        推断下班 22:00 > 19:00 → 保持 22:00，total_hours = 13h。
        """
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=start_time, source="auto", required_hours=8.0
        )

        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 22, 0, 0))

        assert result is True
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record["end_time"] == datetime(2026, 7, 14, 22, 0, 0).strftime(DT_FORMAT)
        assert record["total_hours"] == 13.0

    def test_aligns_to_off_time_floor(self, tracking_service: TrackingService) -> None:
        """推断下班早于 off_time_floor → 对齐到 floor（默认 19:00）。"""
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=start_time, source="auto", required_hours=8.0
        )

        # 18:00 早于 19:00 → 对齐到 19:00
        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 18, 0, 0))

        assert result is True
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record["end_time"] == datetime(2026, 7, 14, 19, 0, 0).strftime(DT_FORMAT)
        assert record["total_hours"] == 10.0

    def test_skips_when_no_start_record(self, tracking_service: TrackingService) -> None:
        """无上班记录 → 不覆盖（下班必须有上班才能算工时）。"""
        target = date(2026, 7, 14)

        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 18, 0, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        # 无上班记录时不应创建新记录
        assert record is None or record.get("end_time") is None

    def test_skips_when_manual_record_exists(self, tracking_service: TrackingService) -> None:
        """已有手动记录 → 不覆盖。"""
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=start_time, source="manual", required_hours=8.0
        )

        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 18, 0, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record.get("end_time") is None
        assert record["source"] == "manual"

    def test_skips_when_end_already_exists(self, tracking_service: TrackingService) -> None:
        """已有下班记录 → 不覆盖。"""
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 9, 0, 0)
        existing_end = datetime(2026, 7, 14, 17, 0, 0)
        tracking_service._worktime_repo.upsert(
            target,
            start_time=start_time,
            end_time=existing_end,
            total_hours=8.0,
            source="auto",
            required_hours=8.0,
        )

        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 18, 0, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record["end_time"] == existing_end.strftime(DT_FORMAT)

    def test_skips_when_leave_record_exists(self, tracking_service: TrackingService) -> None:
        """已有请假记录 → 不覆盖。"""
        target = date(2026, 7, 14)
        tracking_service._worktime_repo.upsert(
            target,
            start_time=datetime(2026, 7, 14, 9, 0, 0),
            source="auto",
            required_hours=8.0,
            leave_type="annual",
        )

        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 18, 0, 0))

        assert result is False
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        assert record.get("end_time") is None

    def test_handles_cross_day_end_time(self, tracking_service: TrackingService) -> None:
        """推断下班时间早于上班时间 → 自动跨天（+1 天）。"""
        target = date(2026, 7, 14)
        start_time = datetime(2026, 7, 14, 22, 0, 0)
        tracking_service._worktime_repo.upsert(
            target, start_time=start_time, source="auto", required_hours=8.0
        )

        # 02:00 早于 22:00 → 跨天到次日 02:00，对齐到 19:00 不生效（02:00 > 19:00?）
        # 实际：02:00 次日 → minute_total = 2*60 = 120 < 19*60=1140 → 对齐到 19:00
        # 但对齐后是次日 19:00，total_hours = 21h
        result = tracking_service.apply_pmset_end_time(target, datetime(2026, 7, 14, 2, 0, 0))

        assert result is True
        record = tracking_service._worktime_repo.get(target)
        assert record is not None
        # 跨天后 end_time 应是次日 19:00
        assert record["end_time"] == datetime(2026, 7, 15, 19, 0, 0).strftime(DT_FORMAT)
        # 22:00 → 次日 19:00 = 21h
        assert record["total_hours"] == 21.0
