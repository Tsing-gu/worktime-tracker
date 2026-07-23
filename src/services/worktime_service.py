# -*- coding: utf-8 -*-
"""
worktime_service - 工时业务编排层
====================================

连接 core 业务逻辑层与 data 数据层，向上为 ui 层提供高层 API。
UI 层只调此服务，不直接操作 database / tracker / calculator。

核心职责:
    - init():               初始化 + 回溯上班时间
    - poll_and_record():    执行轮询 + 持久化活动记录 + 处理上下班事件
    - get_today_status():   获取今日实时状态
    - get_period_stats():   获取本期工时统计
    - get_month_stats():    获取本月工时统计
    - manual_off():         手动下班
    - resume_after_off():   下班后恢复计时
    - check_yesterday():     次日确认检查
    - get_settings/update_settings: 设置读写

版本: 0.8.0
"""

from datetime import datetime, date, timedelta
from typing import Optional

from src.config import (
    SETTING_DAILY_REQUIRED_HOURS,
    SETTING_WEEKLY_WORK_DAYS,
    SETTING_OFF_THRESHOLD_MINUTES,
    SETTING_OFF_TIME_FLOOR,
    SETTING_WORK_START_FLOOR,
    SETTING_NOTIFY_ON_TARGET,
    SETTING_NOTIFY_ON_OFF,
    SETTING_HOLIDAY_AUTO_EXCLUDE,
    SETTING_OFFICE_NETWORK_DOMAIN,
    SETTING_ONLY_OFFICE_TIME,
    LEAVE_TYPES,
    HOLIDAY_API_URLS,
    HOLIDAY_CACHE_FILE,
)
from src.data.models import TodayStatus, PeriodStats, WeekStats
from src.data.settings_repo import SettingsRepository
from src.data.activity_repo import ActivityRepository
from src.data.worktime_repo import DailyWorktimeRepository
from src.data.holiday_repo import HolidayRepository
from src.core.tracker import WorkTracker, PollResult
from src.core.calculator import WorktimeCalculator
from src.core.holiday_service import HolidayService
from src.core.date_utils import compute_work_date
from src.services.export_service import WorktimeExporter
from src.utils.system import get_first_active_from_pmset, get_network_status


class WorktimeService:
    """工时业务编排服务。

    封装 tracker + calculator + database 的完整业务流程，
    UI 层只需调用此服务，不直接操作底层模块。

    使用方式:
        service = WorktimeService()
        service.init()                      # 初始化
        result = service.poll_and_record()   # 轮询
        status = service.get_today_status()  # 获取状态
    """

    def __init__(self):
        """初始化服务，创建内部 tracker 实例和各仓储/计算器。"""
        self.tracker = WorkTracker()
        self.current_work_date: Optional[date] = None
        self._checked_yesterday = False
        self._activities_cleaned_date: Optional[date] = None

        # 仓储实例
        self.settings_repo = SettingsRepository()
        self.activity_repo = ActivityRepository()
        self.worktime_repo = DailyWorktimeRepository()
        self.holiday_repo = HolidayRepository()

        # 节假日服务（注入 holiday_repo）
        self.holiday_service = HolidayService(
            api_urls=HOLIDAY_API_URLS,
            cache_file=HOLIDAY_CACHE_FILE,
            holiday_repo=self.holiday_repo,
        )

        # 计算器（延迟初始化，需要从 DB 读取配置后才能构建）
        self._calculator: Optional[WorktimeCalculator] = None

    # ─── 初始化 ────────────────────────────────────────────

    def init(self):
        """初始化数据库 + 节假日 + 回溯上班时间。"""
        from src.data.database import Database
        Database.init()
        today = date.today()
        self.holiday_service.ensure_loaded(today.year)
        self.current_work_date = compute_work_date(datetime.now())
        office_domain = self.settings_repo.get(SETTING_OFFICE_NETWORK_DOMAIN, "")
        at_office = get_network_status(office_domain)["at_office"]
        self.ensure_start(at_office=at_office)

    def ensure_start(self, at_office: bool = True):
        """回溯或校验当天上班时间。

        统一入口，通过 tracker.check_start_recorded() 按优先级判定:
            1. 已有手动记录 → 不覆盖
            2. 已有自动记录 → 不覆盖
            3. 无记录 + activity_events 有活跃记录 → 取最早活跃时间回填
            4. 以上都不满足 → 静默等待下一次轮询

        Args:
            at_office: 当前是否在公司网络（仅用于决定是否查 at_office 筛选条件）
        """
        only_office = self.settings_repo.get(SETTING_ONLY_OFFICE_TIME, "1") == "1"

        now = datetime.now()
        work_date = compute_work_date(now)
        daily = self.worktime_repo.get(work_date)
        work_start_floor = self.settings_repo.get(SETTING_WORK_START_FLOOR, "06:00")

        existing_start = None
        existing_source = None
        existing_end = None
        if daily:
            if daily.get("start_time"):
                existing_start = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
            existing_source = daily.get("source")
            if daily.get("end_time"):
                existing_end = datetime.strptime(daily["end_time"], "%Y-%m-%d %H:%M:%S")

        # 从 activity_events 查最早活跃记录
        if only_office:
            first_active = self.activity_repo.get_first_active_at_office(work_date)
        else:
            first_active = self.activity_repo.get_first_active(work_date)

        start_to_record = self.tracker.check_start_recorded(
            now=now,
            work_start_floor=work_start_floor,
            existing_start=existing_start,
            existing_source=existing_source,
            existing_end_time=existing_end,
            first_active=first_active,
        )

        if start_to_record:
            daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
            self.worktime_repo.upsert(
                work_date, start_time=start_to_record, source="auto",
                required_hours=daily_required,
            )

    # ─── 轮询 + 持久化 ────────────────────────────────────

    def poll_and_record(self) -> PollResult:
        """执行一次完整轮询: 读取 HID → 记录活动 → 判定事件 → 持久化。"""
        now = datetime.now()

        # 读取当前 HID 状态（跨天补录用，需在 reset 之前读取）
        from src.utils.system import get_hid_idle_seconds, is_currently_active, get_network_status, get_last_active_time
        idle = get_hid_idle_seconds()

        # 跨天检测
        new_work_date = compute_work_date(now)
        if new_work_date != self.current_work_date:
            # 补录昨天未记录的下班时间（睡眠跨天场景）
            self._backfill_off_time(self.current_work_date, now, idle)
            self.tracker.reset_for_new_day()
            self.current_work_date = new_work_date

        active = is_currently_active(idle)

        # 检测网络位置（与 HID 检测并行）
        office_domain = self.settings_repo.get(SETTING_OFFICE_NETWORK_DOMAIN, "")
        at_office = get_network_status(office_domain)["at_office"]

        # 持久化活动记录
        self.activity_repo.record(now, idle, active, at_office=at_office)

        # 每天首次轮询时清理过期活动记录（保留 14 天）
        today = now.date()
        if self._activities_cleaned_date != today:
            self.activity_repo.cleanup(days=14)
            self._activities_cleaned_date = today

        # 获取今日 DB 记录
        work_date = compute_work_date(now)
        daily = self.worktime_repo.get(work_date)

        start_time = None
        daily_end_time = None
        daily_source = "auto"
        if daily:
            if daily.get("start_time"):
                start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
            if daily.get("end_time"):
                daily_end_time = datetime.strptime(daily["end_time"], "%Y-%m-%d %H:%M:%S")
            daily_source = daily.get("source", "auto")

        # 如果 DB 中无上班记录且 tracker 未记录上班 → 调用 ensure_start 补录
        if not start_time and not self.tracker.is_started():
            self.ensure_start(at_office=at_office)
            daily = self.worktime_repo.get(work_date)
            if daily and daily.get("start_time"):
                start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")

        # 读取设置
        off_threshold = float(self.settings_repo.get(SETTING_OFF_THRESHOLD_MINUTES, "60"))
        off_floor = self.settings_repo.get(SETTING_OFF_TIME_FLOOR, "19:00")
        daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))

        # 调用 tracker 纯逻辑判定
        result = self.tracker.poll(
            now=now,
            start_time=start_time,
            daily_end_time=daily_end_time,
            daily_source=daily_source,
            off_threshold_minutes=off_threshold,
            off_time_floor=off_floor,
            daily_required_hours=daily_required,
        )

        # 根据 event 类型持久化
        if result.event == "off":
            self.worktime_repo.upsert(
                work_date,
                end_time=result.off_time,
                total_hours=result.worked_hours,
                required_hours=daily_required,
                is_confirmed=0,
                source="auto",
            )

        return result

    def _backfill_off_time(self, prev_date, now: datetime, idle: float):
        """跨天时补录前一天未记录的下班时间。

        睡眠跨天场景：用户晚上合盖睡眠，次日唤醒时跨天重置抢在下班检测之前，
        导致前一天的 end_time 永远为 NULL。此方法在 reset_for_new_day 之前调用，
        用 now - idle 推算最后一次活动时刻作为下班时间。

        仅当：前一天有 start_time 且无 end_time 且未手动下班时补录。
        """
        if prev_date is None:
            return

        daily = self.worktime_repo.get(prev_date)
        if not daily or not daily.get("start_time") or daily.get("end_time"):
            return
        if daily.get("source") == "manual":
            return

        start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
        off_time = get_last_active_time(idle, now) if idle >= 0 else None
        if off_time is None:
            return

        # off_time 不应早于 start_time（正常不会，防御性检查）
        if off_time <= start_time:
            return

        # 读取下班时间下限设置，对齐到下限
        off_floor = self.settings_repo.get(SETTING_OFF_TIME_FLOOR, "19:00")
        off_floor_h, off_floor_m = map(int, off_floor.split(":"))
        off_total_min = off_time.hour * 60 + off_time.minute
        floor_total_min = off_floor_h * 60 + off_floor_m
        if off_total_min < floor_total_min:
            off_time = off_time.replace(hour=off_floor_h, minute=off_floor_m, second=0, microsecond=0)

        total_hours = (off_time - start_time).total_seconds() / 3600.0
        daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        self.worktime_repo.upsert(
            prev_date,
            end_time=off_time,
            total_hours=total_hours,
            required_hours=daily_required,
            is_confirmed=0,
            source="auto",
        )

    # ─── 手动下班 ──────────────────────────────────────────

    def manual_off(self) -> PollResult:
        """手动下班: 以当前时间记为下班时间并持久化。"""
        now = datetime.now()
        work_date = compute_work_date(now)
        daily = self.worktime_repo.get(work_date)

        if not daily or not daily.get("start_time"):
            return PollResult(event="no_start")

        start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
        result = self.tracker.manual_off_work(start_time, now)

        daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        self.worktime_repo.upsert(
            work_date,
            end_time=result.off_time,
            total_hours=result.worked_hours,
            required_hours=daily_required,
            source="manual",
            is_confirmed=1,
        )

        return result

    # ─── 恢复计时（下班后回来） ────────────────────────────

    def resume_after_off(self):
        """下班后用户回来，确认恢复计时。

        通过 worktime_repo.clear_end_time 消除下班状态，替代裸 SQL。
        """
        work_date = compute_work_date(datetime.now())
        self.worktime_repo.clear_end_time(work_date)
        self.tracker.resume_after_off()

    # ─── 今日状态 ──────────────────────────────────────────

    def get_today_status(self) -> TodayStatus:
        """获取今日实时工时状态。"""
        today = compute_work_date(datetime.now())
        daily = self.worktime_repo.get(today)
        daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        return self._get_calculator().today_status(today, daily, now=datetime.now())

    # ─── 本期统计 ────────────────────────────────────────────

    def get_period_stats(self) -> PeriodStats:
        """获取本期工时统计。"""
        today = compute_work_date(datetime.now())
        calc = self._get_calculator()
        from src.core.date_utils import get_period_range
        holidays = self.holiday_repo.get_all()
        period = get_period_range(today, holidays, calc.weekly_work_days)
        if period is None:
            return PeriodStats(is_rest=True)
        period_start, period_end = period
        records = self.worktime_repo.get_range(period_start, period_end)
        return calc.period_stats(today, records, now=datetime.now())

    # ─── 月统计 ────────────────────────────────────────────

    def get_month_stats(self) -> PeriodStats:
        """获取本月工时统计。"""
        today = compute_work_date(datetime.now())
        from src.core.date_utils import get_month_range
        month_start, month_end = get_month_range(today)
        records = self.worktime_repo.get_range(month_start, month_end)
        return self._get_calculator().month_stats(today, records, now=datetime.now())

    # ─── 次日确认 ──────────────────────────────────────────

    def check_yesterday(self) -> Optional[tuple]:
        """检查是否需要弹出次日确认提醒。"""
        today = compute_work_date(datetime.now())
        prev = self._get_calculator().previous_workday(today)

        if prev is None:
            self._checked_yesterday = True
            return None

        daily = self.worktime_repo.get(prev)

        if daily and daily.get("start_time"):
            self._checked_yesterday = True
            return (prev, daily)
        else:
            self._checked_yesterday = True
            return None

    def should_check_yesterday(self) -> bool:
        """是否需要检查次日确认。"""
        return not self._checked_yesterday

    def confirm_yesterday(self, prev_date: date, end_time: datetime):
        """确认前一天的下班时间并持久化。"""
        daily = self.worktime_repo.get(prev_date)
        if daily and daily.get("start_time"):
            start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
            if end_time < start_time:
                end_time += timedelta(days=1)
            total = (end_time - start_time).total_seconds() / 3600.0
            self.worktime_repo.upsert(
                prev_date, end_time=end_time, total_hours=total, is_confirmed=1,
            )
        else:
            self.worktime_repo.upsert(prev_date, is_confirmed=1)

    def skip_yesterday(self, prev_date: date):
        """跳过次日确认（标记为已确认但不修改数据）。"""
        self.worktime_repo.upsert(prev_date, is_confirmed=1)

    # ─── 请假 ──────────────────────────────────────────────

    def mark_leave(self, leave_date: date, leave_type: str):
        """标记请假。"""
        type_name = LEAVE_TYPES.get(leave_type, leave_type)
        self.worktime_repo.upsert(
            leave_date, leave_type=leave_type, note=f"请假-{type_name}"
        )

    # ─── 手动补录 ──────────────────────────────────────────

    def manual_record(self, work_dt: date, start_str: str, end_str: str) -> float:
        """手动补录某天的上下班时间。"""
        try:
            sh, sm = map(int, start_str.strip().split(":"))
            eh, em = map(int, end_str.strip().split(":"))
            start_dt = datetime(work_dt.year, work_dt.month, work_dt.day, sh, sm)
            end_dt = datetime(work_dt.year, work_dt.month, work_dt.day, eh, em)
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
            total = (end_dt - start_dt).total_seconds() / 3600.0
            daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
            self.worktime_repo.upsert(
                work_dt, start_time=start_dt, end_time=end_dt,
                total_hours=total, required_hours=daily_required,
                source="manual", is_confirmed=1,
            )
            return total
        except Exception as e:
            raise ValueError(f"时间格式不正确：{e}")

    # ─── 修改上班时间 ──────────────────────────────────────

    def get_pmset_start_time(self) -> Optional[datetime]:
        """从 pmset 日志读取今天最早的 UserIsActive 事件时间。"""
        work_date = compute_work_date(datetime.now())
        work_start_floor = self.settings_repo.get(SETTING_WORK_START_FLOOR, "06:00")
        return get_first_active_from_pmset(work_date, work_start_floor)

    def edit_start_time(self, start_str: str) -> datetime:
        """修改今日上班时间。"""
        today = compute_work_date(datetime.now())
        try:
            sh, sm = map(int, start_str.strip().split(":"))
            floor_str = self.settings_repo.get(SETTING_WORK_START_FLOOR, "06:00")
            fh, fm = map(int, floor_str.split(":"))
            if sh < fh or (sh == fh and sm < fm):
                new_start = datetime(today.year, today.month, today.day, fh, fm)
            else:
                new_start = datetime(today.year, today.month, today.day, sh, sm)
            self.worktime_repo.upsert(today, start_time=new_start, source="manual")
            return new_start
        except Exception as e:
            raise ValueError(f"请输入 HH:MM 格式，如 09:30\n\n错误：{e}")

    # ─── 清除记录 ──────────────────────────────────────────

    def clear_record(self, work_date_str: str):
        """删除指定日期的工时记录。"""
        self.worktime_repo.delete(work_date_str)

    # ─── 设置读写 ──────────────────────────────────────────

    def get_settings(self) -> dict:
        """读取全部设置。"""
        return self.settings_repo.get_all()

    def update_settings(self, values: dict):
        """批量更新设置。"""
        for key, value in values.items():
            self.settings_repo.set(key, value)
        # 改设置后更新当天记录的 required_hours
        now = datetime.now()
        work_date = compute_work_date(now)
        daily = self.worktime_repo.get(work_date)
        if daily and daily.get("start_time"):
            daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
            self.worktime_repo.upsert(work_date, required_hours=daily_required)
        # 重置计算器缓存（配置变了）
        self._calculator = None

    def get_setting(self, key: str, default: str = "") -> str:
        """读取单个设置值（供 UI 层使用）。"""
        return self.settings_repo.get(key, default)

    def get_required_hours(self) -> float:
        """获取每日工时要求。"""
        return float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))

    # ─── 数据查询（供日历等使用） ──────────────────────────

    def get_date_range_worktime(self, start: date, end: date) -> list:
        """获取日期范围内的工时记录。"""
        return self.worktime_repo.get_range(start, end)

    def get_all_holidays(self) -> list:
        """获取全部节假日缓存。"""
        return self.holiday_repo.get_all()

    def get_daily_worktime(self, work_dt: date) -> Optional[dict]:
        """获取指定日期的工时记录。"""
        return self.worktime_repo.get(work_dt)

    def get_exporter(self) -> WorktimeExporter:
        """获取导出器实例。"""
        return WorktimeExporter(self.worktime_repo)

    # ─── 内部工具 ──────────────────────────────────────────

    def _get_calculator(self) -> WorktimeCalculator:
        """懒加载计算器，从 DB 读取配置后构建。"""
        if self._calculator is None:
            holidays = self.holiday_repo.get_all()
            daily_required = float(self.settings_repo.get(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
            holiday_auto = self.settings_repo.get(SETTING_HOLIDAY_AUTO_EXCLUDE, "1") == "1"
            weekly_work_days = int(self.settings_repo.get(SETTING_WEEKLY_WORK_DAYS, "5"))
            self._calculator = WorktimeCalculator(
                holidays=holidays,
                daily_required=daily_required,
                holiday_auto_exclude=holiday_auto,
                weekly_work_days=weekly_work_days,
            )
        return self._calculator
