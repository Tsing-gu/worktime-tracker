# -*- coding: utf-8 -*-
"""
worktime_service - 工时业务编排层
====================================

连接 core 业务逻辑层与 data 数据层，向上为 ui 层提供高层 API。

核心职责:
    - poll_and_record():  执行轮询 + 持久化活动记录 + 处理上下班事件
    - get_today_status():  获取今日实时状态
    - get_week_stats():    获取周工时统计
    - get_month_stats():   获取月工时统计
    - manual_off():        手动下班
    - resume_after_off():  下班后恢复计时
    - check_yesterday():   次日确认检查
    - ensure_start():      启动时回溯上班时间

版本: 0.4.2
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
    LEAVE_TYPES,
)
from src.data import database
from src.data.models import WeekStats, MonthStats, TodayStatus, PeriodStats
from src.core.tracker import WorkTracker, PollResult
from src.core import calculator
from src.core import holiday
from src.utils.system import get_first_active_from_pmset


class WorktimeService:
    """
    工时业务编排服务。

    封装 tracker + calculator + database 的完整业务流程，
    UI 层只需调用此服务，不直接操作底层模块。

    使用方式:
        service = WorktimeService()
        service.init()                      # 初始化
        result = service.poll_and_record()   # 轮询
        status = service.get_today_status()  # 获取状态
    """

    def __init__(self):
        """初始化服务，创建内部 tracker 实例。"""
        self.tracker = WorkTracker()
        self.current_work_date: Optional[date] = None
        self.checked_yesterday = False  # 是否已检查次日确认
        self._activities_cleaned_date: Optional[date] = None  # 当天是否已清理过期活动记录

    # ─── 初始化 ────────────────────────────────────────────

    def init(self):
        """
        初始化数据库 + 节假日 + 回溯上班时间。

        应在程序启动时调用一次。
        """
        database.init_db()
        today = date.today()
        holiday.ensure_holidays_loaded(today.year)
        self.current_work_date = database.compute_work_date(datetime.now())
        self.ensure_start()

    def ensure_start(self):
        """
        回溯或校验当天上班时间。

        统一入口，通过 tracker.check_start_recorded() 按优先级判定:
            1. DB 已有手动记录 → 不覆盖
            2. DB 已有自动记录 + pmset 更早 → 修正
            3. DB 已有自动记录 + 已下班 → 不覆盖
            4. 无 DB 记录 + pmset 有记录 → 回填
            5. 无 DB 记录 + 当前 HID 活跃 → 回推
            6. 以上都不满足 → 静默等待下一次轮询

        pmset 日志可能被截断（日志只保留最近条目），
        此时不报错，等待下次轮询用 HID 活动回推。
        """
        now = datetime.now()
        work_date = database.compute_work_date(now)
        daily = database.get_daily_worktime(work_date)
        work_start_floor = database.get_setting(SETTING_WORK_START_FLOOR, "06:00")

        existing_start = None
        existing_source = None
        existing_end = None
        if daily:
            if daily.get("start_time"):
                existing_start = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
            existing_source = daily.get("source")
            if daily.get("end_time"):
                existing_end = datetime.strptime(daily["end_time"], "%Y-%m-%d %H:%M:%S")

        pmset_start = get_first_active_from_pmset(work_date, work_start_floor)

        start_to_record = self.tracker.check_start_recorded(
            now=now,
            work_start_floor=work_start_floor,
            existing_start=existing_start,
            existing_source=existing_source,
            existing_end_time=existing_end,
            pmset_start=pmset_start,
        )

        # 如果 tracker 返回了需要记录的上班时间 → 写入 DB（同时写入 required_hours 快照）
        if start_to_record:
            daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
            database.upsert_daily_worktime(work_date, start_time=start_to_record, source="auto", required_hours=daily_required)

    # ─── 轮询 + 持久化 ────────────────────────────────────

    def poll_and_record(self) -> PollResult:
        """
        执行一次完整轮询: 读取 HID → 记录活动 → 判定事件 → 持久化。

        上班记录统一由 ensure_start() → check_start_recorded() 处理，
        本方法不再自行写入上班时间，避免绕过优先级判定。

        Returns:
            PollResult 实例，包含事件类型和关联数据
        """
        now = datetime.now()

        # 跨天检测
        new_work_date = database.compute_work_date(now)
        if new_work_date != self.current_work_date:
            self.tracker.reset_for_new_day()
            self.current_work_date = new_work_date

        # 读取当前 HID 状态
        from src.utils.system import get_hid_idle_seconds, is_currently_active
        idle = get_hid_idle_seconds()
        active = is_currently_active(idle)

        # 持久化活动记录
        database.record_activity(now, idle, active)

        # 每天首次轮询时清理过期活动记录（保留 14 天），避免频繁删表
        today = now.date()
        if self._activities_cleaned_date != today:
            database.cleanup_old_activities(days=14)
            self._activities_cleaned_date = today

        # 获取今日 DB 记录
        work_date = database.compute_work_date(now)
        daily = database.get_daily_worktime(work_date)

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
        if not start_time and not self.tracker.start_recorded:
            self.ensure_start()
            # 重新读取 DB（ensure_start 可能已写入）
            daily = database.get_daily_worktime(work_date)
            if daily and daily.get("start_time"):
                start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")

        # 读取设置
        off_threshold = float(database.get_setting(SETTING_OFF_THRESHOLD_MINUTES, "60"))
        off_floor = database.get_setting(SETTING_OFF_TIME_FLOOR, "19:00")
        daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))

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
            # 自动下班 → 写入 end_time + total_hours + required_hours
            database.upsert_daily_worktime(
                work_date,
                end_time=result.off_time,
                total_hours=result.worked_hours,
                required_hours=daily_required,
                is_confirmed=0,
                source="auto",
            )
        # "back" 事件由 UI 层弹窗确认后调用 resume_after_off()
        # "start"、"target_reached"、"manual_off" 等事件由调用方决定后续操作

        return result

    # ─── 手动下班 ──────────────────────────────────────────

    def manual_off(self) -> PollResult:
        """
        手动下班: 以当前时间记为下班时间并持久化。

        Returns:
            PollResult(event="manual_off", ...)
        """
        now = datetime.now()
        work_date = database.compute_work_date(now)
        daily = database.get_daily_worktime(work_date)

        if not daily or not daily.get("start_time"):
            return PollResult(event="no_start")

        start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
        result = self.tracker.manual_off_work(start_time, now)

        # 持久化（写入 required_hours 快照）
        daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        database.upsert_daily_worktime(
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
        """
        下班后用户回来，确认恢复计时。

        操作:
            1. 删除 DB 中的 end_time 和 total_hours（恢复为未下班状态）
            2. 重置 tracker 的下班/回来标记
        """
        now = datetime.now()
        work_date = database.compute_work_date(now)
        # 清除下班时间，恢复为"工作中"状态
        # 使用 UPDATE 显式置空 end_time 和 total_hours
        conn = database.get_connection()
        conn.execute(
            "UPDATE daily_worktime SET end_time = NULL, total_hours = NULL WHERE work_date = ?",
            (work_date.isoformat(),),
        )
        conn.commit()
        conn.close()
        # 重置 tracker 状态
        self.tracker.resume_after_off()

    # ─── 今日状态 ──────────────────────────────────────────

    def get_today_status(self) -> TodayStatus:
        """
        获取今日实时工时状态。

        Returns:
            TodayStatus 对象
        """
        today = database.compute_work_date(datetime.now())
        daily = database.get_daily_worktime(today)
        daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        return calculator.get_today_status(today, daily, daily_required, now=datetime.now())

    # ─── 本期统计 ────────────────────────────────────────────

    def get_period_stats(self) -> PeriodStats:
        """
        获取本期工时统计。

        本期 = 两个连续非工作日段之间的工作日区间。

        Returns:
            PeriodStats 对象
        """
        today = database.compute_work_date(datetime.now())
        from src.core.calculator import get_period_range
        holidays = database.get_all_holidays()
        daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        holiday_auto = database.get_setting(SETTING_HOLIDAY_AUTO_EXCLUDE, "1") == "1"

        period = get_period_range(today, holidays)
        if period is None:
            return PeriodStats(is_rest=True)
        period_start, period_end = period

        records = database.get_date_range_worktime(period_start, period_end)

        return calculator.get_period_stats(
            today, records, holidays, daily_required, holiday_auto,
            now=datetime.now(),
        )

    # ─── 月统计 ────────────────────────────────────────────

    def get_month_stats(self) -> PeriodStats:
        """
        获取本月工时统计。

        Returns:
            PeriodStats 对象
        """
        today = database.compute_work_date(datetime.now())
        from src.core.calculator import get_month_range
        month_start, month_end = get_month_range(today)
        records = database.get_date_range_worktime(month_start, month_end)
        holidays = database.get_all_holidays()
        daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        holiday_auto = database.get_setting(SETTING_HOLIDAY_AUTO_EXCLUDE, "1") == "1"

        return calculator.get_month_stats(
            today, records, holidays, daily_required, holiday_auto,
            now=datetime.now(),
        )

    # ─── 次日确认 ──────────────────────────────────────────

    def check_yesterday(self) -> Optional[tuple]:
        """
        检查是否需要弹出次日确认提醒。

        返回需要确认的前一个工作日及其记录，供 UI 弹窗使用。
        如果已确认或无需确认，返回 None 并标记 self.checked_yesterday = True。

        Returns:
            (prev_workday, daily_record) 元组，或 None
        """
        today = date.today()
        holidays = database.get_all_holidays()
        holiday_auto = database.get_setting(SETTING_HOLIDAY_AUTO_EXCLUDE, "1") == "1"
        prev = calculator.get_previous_workday(today, holidays, holiday_auto)

        if prev is None:
            self.checked_yesterday = True
            return None

        daily = database.get_daily_worktime(prev)
        if daily and daily.get("is_confirmed") == 1:
            self.checked_yesterday = True
            return None

        if daily and daily.get("start_time"):
            self.checked_yesterday = True
            return (prev, daily)
        else:
            self.checked_yesterday = True
            return None

    def confirm_yesterday(self, prev_date: date, end_time: datetime):
        """
        确认前一天的下班时间并持久化。

        Args:
            prev_date: 前一个工作日日期
            end_time:  用户确认/修改后的下班时间
        """
        daily = database.get_daily_worktime(prev_date)
        if daily and daily.get("start_time"):
            start_time = datetime.strptime(daily["start_time"], "%Y-%m-%d %H:%M:%S")
            if end_time < start_time:
                end_time += timedelta(days=1)  # 跨天处理
            total = (end_time - start_time).total_seconds() / 3600.0
            database.upsert_daily_worktime(
                prev_date, end_time=end_time, total_hours=total, is_confirmed=1,
            )
        else:
            database.upsert_daily_worktime(prev_date, is_confirmed=1)

    def skip_yesterday(self, prev_date: date):
        """
        跳过次日确认（标记为已确认但不修改数据）。

        Args:
            prev_date: 前一个工作日日期
        """
        database.upsert_daily_worktime(prev_date, is_confirmed=1)

    # ─── 请假 ──────────────────────────────────────────────

    def mark_leave(self, leave_date: date, leave_type: str):
        """
        标记请假。

        Args:
            leave_date:  请假日期
            leave_type:  请假类型 (annual/sick/personal/compensatory)
        """
        type_name = LEAVE_TYPES.get(leave_type, leave_type)
        database.upsert_daily_worktime(
            leave_date, leave_type=leave_type, note=f"请假-{type_name}"
        )

    # ─── 手动补录 ──────────────────────────────────────────

    def manual_record(self, work_dt: date, start_str: str, end_str: str) -> float:
        """
        手动补录某天的上下班时间。

        Args:
            work_dt:  工作日日期
            start_str: 上班时间 "HH:MM"
            end_str:   下班时间 "HH:MM"

        Returns:
            工时（小时）

        Raises:
            ValueError: 时间格式不正确
        """
        try:
            sh, sm = map(int, start_str.strip().split(":"))
            eh, em = map(int, end_str.strip().split(":"))
            start_dt = datetime(work_dt.year, work_dt.month, work_dt.day, sh, sm)
            end_dt = datetime(work_dt.year, work_dt.month, work_dt.day, eh, em)
            if end_dt < start_dt:
                end_dt += timedelta(days=1)  # 跨天处理
            total = (end_dt - start_dt).total_seconds() / 3600.0
            daily_required = float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
            database.upsert_daily_worktime(
                work_dt, start_time=start_dt, end_time=end_dt,
                total_hours=total, required_hours=daily_required,
                source="manual", is_confirmed=1,
            )
            return total
        except Exception as e:
            raise ValueError(f"时间格式不正确：{e}")

    # ─── 修改上班时间 ──────────────────────────────────────

    def edit_start_time(self, start_str: str) -> datetime:
        """
        修改今日上班时间。

        Args:
            start_str: 上班时间 "HH:MM"

        Returns:
            更新后的上班时间 datetime

        Raises:
            ValueError: 时间格式不正确
        """
        today = date.today()
        try:
            sh, sm = map(int, start_str.strip().split(":"))
            floor_str = database.get_setting(SETTING_WORK_START_FLOOR, "06:00")
            fh, fm = map(int, floor_str.split(":"))
            if sh < fh or (sh == fh and sm < fm):
                new_start = datetime(today.year, today.month, today.day, fh, fm)
            else:
                new_start = datetime(today.year, today.month, today.day, sh, sm)
            database.upsert_daily_worktime(today, start_time=new_start, source="manual")
            return new_start
        except Exception as e:
            raise ValueError(f"请输入 HH:MM 格式，如 09:30\n\n错误：{e}")

    # ─── 清除记录 ──────────────────────────────────────────

    def clear_record(self, work_date_str: str):
        """
        删除指定日期的工时记录。

        Args:
            work_date_str: 工作日日期字符串 "YYYY-MM-DD"
        """
        database.delete_daily_worktime(work_date_str)

    # ─── 数据查询（供日历等使用） ──────────────────────────

    def get_date_range_worktime(self, start: date, end: date) -> list:
        """
        获取日期范围内的工时记录。

        Args:
            start: 起始日期
            end:   结束日期

        Returns:
            dict 列表
        """
        return database.get_date_range_worktime(start, end)

    def get_all_holidays(self) -> list:
        """
        获取全部节假日缓存。

        Returns:
            dict 列表
        """
        return database.get_all_holidays()

    def get_daily_worktime(self, work_dt: date) -> Optional[dict]:
        """
        获取指定日期的工时记录。

        Args:
            work_dt: 工作日日期

        Returns:
            dict 或 None
        """
        return database.get_daily_worktime(work_dt)
