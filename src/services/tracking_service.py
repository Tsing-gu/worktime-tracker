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
from datetime import date, datetime, timedelta

from src.core.tracker import PollResult, WorkTrackerCore
from src.data.activity_repo import ActivityRepository
from src.data.database import DT_FORMAT
from src.data.models import PmsetDailySummary
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.holiday_service import HolidayService
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.utils.date_utils import compute_work_date
from src.utils.system import (
    get_active_periods_from_pmset,
    get_first_active_from_pmset,
    get_hid_idle_seconds,
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
            self._backfill_off_time(self.current_work_date, now)
            self.tracker.reset_for_new_day()
            self.current_work_date = new_work_date
            self._record.reset_yesterday_flag()

        active = is_currently_active(idle)
        settings = self._settings.get()
        at_office = get_network_status(settings.office_network_domain)["at_office"]

        # HID 读取失败提示：only_office=False 时无降级路径，仅靠跨天补录
        if idle < 0:
            logger.warning(
                "HID 空闲时间读取失败（ioreg 返回异常），下班判定将仅靠网络门控触发"
                "（only_office=%s）",
                settings.only_office_time,
            )

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
            idle=idle,
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

    def _backfill_off_time(self, prev_date: date | None, now: datetime) -> None:
        """跨天时补录前一天未记录的下班时间（睡眠/关机跨天场景）。

        从 ``activity_events`` 表查询前一天的最后一个 active 记录作为下班时间，
        相比 ``now - idle``（HIDIdleTime）能正确处理关机场景
        （关机后 HIDIdleTime 重置为 0，``now - idle`` 推算会得到错误时间）。
        """
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
            # 从 activity_events 表查询最后一条 active 记录，准确反映最后操作时间
            # 修复: 原 now - idle 在关机场景下错误（HIDIdleTime 重置为 0）
            last_active = self._activity_repo.get_last_active(prev_date)
            if last_active and last_active > start_time:
                off_time = last_active

        if off_time is None or off_time <= start_time:
            return

        # 次日凌晨属于前一工作日的延续，不得对齐到未来的当日下班时间。
        off_floor_h, off_floor_m = map(int, settings.off_time_floor.split(":"))
        off_total_min = off_time.hour * 60 + off_time.minute
        floor_total_min = off_floor_h * 60 + off_floor_m
        is_overnight = off_time.date() > prev_date
        if off_time > now:
            logger.warning("跨天补录时间晚于检测时间，跳过：%s > %s", off_time, now)
            return
        if not is_overnight and off_total_min < floor_total_min:
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

    # ─── pmset 近 7 天推断 ────────────────────────────────

    def get_recent_pmset_summary(self, days: int = 7) -> list[PmsetDailySummary]:
        """读取近 N 天的 pmset 推断上下班时间，并与 DB 已有记录对比。

        从今天往前推 N 天，对每个日期调用 get_active_periods_from_pmset，
        并查 daily_worktime 表标记是否已有上班/下班记录。

        注意：pmset 仅能推断用户使用电脑的情况，无法区分公司/家里，
        在家用电脑时下班时间可能偏晚。

        Args:
            days: 天数（默认 7）

        Returns:
            PmsetDailySummary 列表，按日期降序排列（今天在最前）
        """
        settings = self._settings.get()
        today = compute_work_date(datetime.now())
        summaries: list[PmsetDailySummary] = []
        for offset in range(days):
            target = today - timedelta(days=offset)
            first_active, last_active = get_active_periods_from_pmset(
                target, settings.work_start_floor
            )
            daily = self._worktime_repo.get(target)
            has_start = bool(daily and daily.get("start_time"))
            has_end = bool(daily and daily.get("end_time"))
            source = daily.get("source") if daily else None
            leave_type = daily.get("leave_type") if daily else None
            summaries.append(
                PmsetDailySummary(
                    work_date=target,
                    first_active=first_active,
                    last_active=last_active,
                    has_start_record=has_start,
                    has_end_record=has_end,
                    source=source,
                    leave_type=leave_type,
                )
            )
        return summaries

    def apply_pmset_start_time(self, work_date: date, start_time: datetime) -> bool:
        """应用 pmset 推断的上班时间到 DB。

        保护策略（不覆盖的场景）：
            - 已有手动记录（source='manual'）→ 不覆盖
            - 已有请假记录（leave_type 非空）→ 不覆盖
            - 已有上班记录（start_time 非空）→ 不覆盖
        否则 → upsert(start_time, source='auto', required_hours)

        Args:
            work_date:   目标工作日
            start_time:  pmset 推断的上班时间

        Returns:
            True=已应用, False=因保护策略被跳过
        """
        daily = self._worktime_repo.get(work_date)
        if daily:
            if daily.get("source") == "manual":
                logger.info("pmset 推断上班时间跳过：%s 已有手动记录", work_date)
                return False
            if daily.get("leave_type"):
                logger.info("pmset 推断上班时间跳过：%s 已请假", work_date)
                return False
            if daily.get("start_time"):
                logger.info("pmset 推断上班时间跳过：%s 已有上班记录", work_date)
                return False

        settings = self._settings.get()
        self._worktime_repo.upsert(
            work_date,
            start_time=start_time,
            source="auto",
            required_hours=settings.daily_required_hours,
        )
        logger.info("pmset 推断上班时间已应用：%s %s", work_date, start_time)
        return True

    def apply_pmset_end_time(self, work_date: date, end_time: datetime) -> bool:
        """应用 pmset 推断的下班时间到 DB。

        保护策略（不覆盖的场景）：
            - 已有手动记录（source='manual'）→ 不覆盖
            - 已有请假记录（leave_type 非空）→ 不覆盖
            - 已有下班记录（end_time 非空）→ 不覆盖
            - 无上班记录（start_time 为空）→ 不覆盖（下班必须有上班才能算工时）
        否则 → upsert(end_time, total_hours, source='auto', is_confirmed=0)

        Args:
            work_date: 目标工作日
            end_time:  pmset 推断的下班时间

        Returns:
            True=已应用, False=因保护策略被跳过
        """
        daily = self._worktime_repo.get(work_date)
        if not daily or not daily.get("start_time"):
            logger.info("pmset 推断下班时间跳过：%s 无上班记录", work_date)
            return False
        if daily.get("source") == "manual":
            logger.info("pmset 推断下班时间跳过：%s 已有手动记录", work_date)
            return False
        if daily.get("leave_type"):
            logger.info("pmset 推断下班时间跳过：%s 已请假", work_date)
            return False
        if daily.get("end_time"):
            logger.info("pmset 推断下班时间跳过：%s 已有下班记录", work_date)
            return False

        start_time = datetime.strptime(daily["start_time"], DT_FORMAT)
        if end_time < start_time:
            end_time += timedelta(days=1)

        # 次日凌晨属于目标工作日的延续，不得对齐到未来的当日下班时间。
        settings = self._settings.get()
        off_floor_h, off_floor_m = map(int, settings.off_time_floor.split(":"))
        off_total_min = end_time.hour * 60 + end_time.minute
        floor_total_min = off_floor_h * 60 + off_floor_m
        if end_time.date() == work_date and off_total_min < floor_total_min:
            end_time = end_time.replace(
                hour=off_floor_h, minute=off_floor_m, second=0, microsecond=0
            )

        total_hours = (end_time - start_time).total_seconds() / 3600.0
        self._worktime_repo.upsert(
            work_date,
            end_time=end_time,
            total_hours=total_hours,
            required_hours=settings.daily_required_hours,
            is_confirmed=0,
            source="auto",
        )
        logger.info("pmset 推断下班时间已应用：%s %s", work_date, end_time)
        return True
