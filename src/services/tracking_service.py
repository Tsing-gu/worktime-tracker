"""
tracking_service - 轮询追踪服务
================================

负责键鼠活动轮询、上下班判定、跨天补录、手动下班/恢复。
从原 WorktimeService 拆分而来，只管追踪相关逻辑。

依赖通过构造期注入：
    - tracker:          WorkTrackerCore 实例
    - activity_repo:    ActivityRepository
    - worktime_repo:    DailyWorktimeRepository
    - settings_service: SettingsService（类型化设置）
    - holiday_service:  HolidayService
    - record_service:   RecordService（跨天时重置次日确认标志）

版本: 0.16.0
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from src.core.tracker import PollResult, WorkTrackerCore
from src.data.activity_repo import ActivityRepository
from src.data.database import DT_FORMAT
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.holiday_service import HolidayService
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.utils.date_utils import compute_work_date
from src.utils.system import (
    get_first_active_from_pmset,
    get_hid_idle_seconds,
    get_last_active_time,
    get_network_status,
    is_currently_active,
)

logger = logging.getLogger(__name__)


class TrackingService:
    """轮询追踪服务。

    管理上班/下班状态机，每 30 秒轮询一次 HID 空闲时间，
    判定上下班事件并持久化到 DB。
    """

    def __init__(
        self,
        tracker: WorkTrackerCore,
        activity_repo: ActivityRepository,
        worktime_repo: DailyWorktimeRepository,
        settings_service: SettingsService,
        holiday_service: HolidayService,
        record_service: RecordService,
    ) -> None:
        self.tracker = tracker
        self._activity_repo = activity_repo
        self._worktime_repo = worktime_repo
        self._settings = settings_service
        self._holiday = holiday_service
        self._record = record_service
        self.current_work_date: date | None = None
        self._activities_cleaned_date: date | None = None

    def init_work_date(self) -> None:
        """设置当前工作日并回溯上班时间（在 ServiceFactory.init_all 中调用）。"""
        self.current_work_date = compute_work_date(datetime.now())
        settings = self._settings.get()
        at_office = get_network_status(settings.office_network_domain)["at_office"]
        self.ensure_start(at_office=at_office)

    def ensure_start(self, at_office: bool = True) -> None:
        """回溯或校验当天上班时间。

        通过 tracker.check_start_recorded() 按优先级判定:
            1. 已有手动/自动记录 → 不覆盖
            2. 无记录 + activity_events 有活跃记录 → 取最早活跃时间回填
            3. 以上都不满足 → 静默等待
        """
        settings = self._settings.get()

        now = datetime.now()
        work_date = compute_work_date(now)
        daily = self._worktime_repo.get(work_date)

        existing_start: datetime | None = None
        existing_source: str | None = None
        existing_end: datetime | None = None
        if daily:
            if daily.get("start_time"):
                existing_start = datetime.strptime(daily["start_time"], DT_FORMAT)
            existing_source = daily.get("source")
            if daily.get("end_time"):
                existing_end = datetime.strptime(daily["end_time"], DT_FORMAT)

        if settings.only_office_time:
            first_active = self._activity_repo.get_first_active(work_date, at_office_only=True)
        else:
            first_active = self._activity_repo.get_first_active(work_date)

        start_to_record = self.tracker.check_start_recorded(
            now=now,
            work_start_floor=settings.work_start_floor,
            existing_start=existing_start,
            existing_source=existing_source,
            existing_end_time=existing_end,
            first_active=first_active,
        )

        if start_to_record:
            self._worktime_repo.upsert(
                work_date,
                start_time=start_to_record,
                source="auto",
                required_hours=settings.daily_required_hours,
            )

    def poll_and_record(self) -> PollResult:
        """执行一次完整轮询: 读取 HID → 记录活动 → 判定事件 → 持久化。"""
        now = datetime.now()
        idle = get_hid_idle_seconds()

        # 跨天检测
        new_work_date = compute_work_date(now)
        if new_work_date != self.current_work_date:
            self._backfill_off_time(self.current_work_date, now, idle)
            self.tracker.reset_for_new_day()
            self.current_work_date = new_work_date
            self._record.reset_yesterday_flag()

        active = is_currently_active(idle)
        settings = self._settings.get()
        at_office = get_network_status(settings.office_network_domain)["at_office"]

        self._activity_repo.record(now, idle, active, at_office=at_office)

        today = now.date()
        if self._activities_cleaned_date != today:
            self._activity_repo.cleanup(days=14)
            self._activities_cleaned_date = today

        work_date = compute_work_date(now)
        daily = self._worktime_repo.get(work_date)

        start_time: datetime | None = None
        daily_end_time: datetime | None = None
        daily_source = "auto"
        if daily:
            if daily.get("start_time"):
                start_time = datetime.strptime(daily["start_time"], DT_FORMAT)
            if daily.get("end_time"):
                daily_end_time = datetime.strptime(daily["end_time"], DT_FORMAT)
            daily_source = daily.get("source", "auto")

        if not start_time and not self.tracker.is_started():
            self.ensure_start(at_office=at_office)
            daily = self._worktime_repo.get(work_date)
            if daily and daily.get("start_time"):
                start_time = datetime.strptime(daily["start_time"], DT_FORMAT)

        result = self.tracker.poll(
            now=now,
            start_time=start_time,
            daily_end_time=daily_end_time,
            daily_source=daily_source,
            off_threshold_minutes=settings.off_threshold_minutes,
            off_time_floor=settings.off_time_floor,
            daily_required_hours=settings.daily_required_hours,
            at_office=at_office,
            only_office=settings.only_office_time,
        )

        if result.event == "off":
            self._worktime_repo.upsert(
                work_date,
                end_time=result.off_time,
                total_hours=result.worked_hours,
                required_hours=settings.daily_required_hours,
                is_confirmed=0,
                source="auto",
            )

        return result

    def _backfill_off_time(self, prev_date: date | None, now: datetime, idle: float) -> None:
        """跨天时补录前一天未记录的下班时间（睡眠跨天场景）。"""
        if prev_date is None:
            return

        daily = self._worktime_repo.get(prev_date)
        if not daily or not daily.get("start_time") or daily.get("end_time"):
            return
        if daily.get("source") == "manual":
            return

        start_time = datetime.strptime(daily["start_time"], DT_FORMAT)
        settings = self._settings.get()

        off_time: datetime | None = None
        if settings.only_office_time:
            last_office = self._activity_repo.get_last_active_at_office(prev_date)
            if last_office and last_office > start_time:
                off_time = last_office
        else:
            if idle >= 0:
                off_time = get_last_active_time(idle, now)

        if off_time is None or off_time <= start_time:
            return

        # 对齐到下班时间下限
        off_floor_h, off_floor_m = map(int, settings.off_time_floor.split(":"))
        off_total_min = off_time.hour * 60 + off_time.minute
        floor_total_min = off_floor_h * 60 + off_floor_m
        if off_total_min < floor_total_min:
            off_time = off_time.replace(
                hour=off_floor_h, minute=off_floor_m, second=0, microsecond=0
            )

        total_hours = (off_time - start_time).total_seconds() / 3600.0
        self._worktime_repo.upsert(
            prev_date,
            end_time=off_time,
            total_hours=total_hours,
            required_hours=settings.daily_required_hours,
            is_confirmed=0,
            source="auto",
        )

    def manual_off(self) -> PollResult:
        """手动下班: 以当前时间记为下班时间并持久化。"""
        now = datetime.now()
        work_date = compute_work_date(now)
        daily = self._worktime_repo.get(work_date)

        if not daily or not daily.get("start_time"):
            return PollResult(event="no_start")

        start_time = datetime.strptime(daily["start_time"], DT_FORMAT)
        result = self.tracker.manual_off_work(start_time, now)

        settings = self._settings.get()
        self._worktime_repo.upsert(
            work_date,
            end_time=result.off_time,
            total_hours=result.worked_hours,
            required_hours=settings.daily_required_hours,
            source="manual",
            is_confirmed=1,
        )
        return result

    def resume_after_off(self) -> None:
        """下班后用户回来，确认恢复计时。"""
        work_date = compute_work_date(datetime.now())
        self._worktime_repo.clear_end_time(work_date)
        self.tracker.resume_after_off()

    def get_pmset_start_time(self) -> datetime | None:
        """从 pmset 日志读取今天最早的 UserIsActive 事件时间。"""
        work_date = compute_work_date(datetime.now())
        settings = self._settings.get()
        return get_first_active_from_pmset(work_date, settings.work_start_floor)

    def edit_start_time(self, start_str: str) -> datetime:
        """修改今日上班时间。"""
        today = compute_work_date(datetime.now())
        try:
            sh, sm = map(int, start_str.strip().split(":"))
            settings = self._settings.get()
            fh, fm = map(int, settings.work_start_floor.split(":"))
            if sh < fh or (sh == fh and sm < fm):
                new_start = datetime(today.year, today.month, today.day, fh, fm)
            else:
                new_start = datetime(today.year, today.month, today.day, sh, sm)
            self._worktime_repo.upsert(today, start_time=new_start, source="manual")
            return new_start
        except Exception as e:
            raise ValueError(f"请输入 HH:MM 格式，如 09:30\n\n错误：{e}") from e
