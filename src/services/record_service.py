"""
record_service - 历史记录服务
============================

负责请假标记、手动补录、清除记录、次日确认等历史记录操作。
从原 WorktimeService 拆分而来，只管记录读写。

版本: 0.16.0
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from src.config import LEAVE_TYPES
from src.data.database import DT_FORMAT
from src.data.holiday_repo import HolidayRepository
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.settings_service import SettingsService
from src.services.stats_service import StatsService
from src.utils.date_utils import compute_work_date

logger = logging.getLogger(__name__)


class RecordService:
    """历史记录服务。

    依赖通过构造期注入：
        - worktime_repo:    DailyWorktimeRepository
        - holiday_repo:     HolidayRepository
        - settings_service: SettingsService
        - stats_service:    StatsService（用于 calculator.previous_workday）
    """

    def __init__(
        self,
        worktime_repo: DailyWorktimeRepository,
        holiday_repo: HolidayRepository,
        settings_service: SettingsService,
        stats_service: StatsService,
    ) -> None:
        self._worktime_repo = worktime_repo
        self._holiday_repo = holiday_repo
        self._settings = settings_service
        self._stats = stats_service
        self._checked_yesterday = False

    # ─── 次日确认 ──────────────────────────────────────────

    def check_yesterday(self) -> tuple | None:
        """检查是否需要弹出次日确认提醒。

        只返回未确认（is_confirmed=0）的记录，已确认的不再弹窗。
        """
        today = compute_work_date(datetime.now())
        prev = self._stats.get_calculator().previous_workday(today)

        if prev is None:
            return None

        daily = self._worktime_repo.get(prev)

        if daily and daily.get("start_time") and not daily.get("is_confirmed", 0):
            return (prev, daily)
        return None

    def should_check_yesterday(self) -> bool:
        """是否需要检查次日确认。"""
        return not self._checked_yesterday

    def mark_yesterday_checked(self) -> None:
        """显式标记次日确认已完成。"""
        self._checked_yesterday = True

    def reset_yesterday_flag(self) -> None:
        """重置次日确认标志（跨天时由 TrackingService 调用）。"""
        self._checked_yesterday = False

    def confirm_yesterday(self, prev_date: date, end_time: datetime) -> None:
        """确认前一天的下班时间并持久化。"""
        daily = self._worktime_repo.get(prev_date)
        if daily and daily.get("start_time"):
            start_time = datetime.strptime(daily["start_time"], DT_FORMAT)
            if end_time < start_time:
                end_time += timedelta(days=1)
            total = (end_time - start_time).total_seconds() / 3600.0
            self._worktime_repo.upsert(
                prev_date,
                end_time=end_time,
                total_hours=total,
                is_confirmed=1,
            )
        else:
            self._worktime_repo.upsert(prev_date, is_confirmed=1)

    def skip_yesterday(self, prev_date: date) -> None:
        """跳过次日确认（标记为已确认但不修改数据）。"""
        self._worktime_repo.upsert(prev_date, is_confirmed=1)

    # ─── 请假 ──────────────────────────────────────────────

    def mark_leave(self, leave_date: date, leave_type: str) -> None:
        """标记请假。"""
        type_name = LEAVE_TYPES.get(leave_type, leave_type)
        self._worktime_repo.upsert(leave_date, leave_type=leave_type, note=f"请假-{type_name}")

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
            daily_required = self._settings.get().daily_required_hours
            self._worktime_repo.upsert(
                work_dt,
                start_time=start_dt,
                end_time=end_dt,
                total_hours=total,
                required_hours=daily_required,
                source="manual",
                is_confirmed=1,
            )
            return total
        except Exception as e:
            raise ValueError(f"时间格式不正确：{e}") from e

    # ─── 清除记录 ──────────────────────────────────────────

    def clear_record(self, work_date_str: str) -> None:
        """删除指定日期的工时记录。"""
        self._worktime_repo.delete(date.fromisoformat(work_date_str))

    # ─── 数据查询（供日历等使用） ──────────────────────────

    def get_daily_worktime(self, work_dt: date) -> dict | None:
        """获取指定日期的工时记录。"""
        return self._worktime_repo.get(work_dt)

    def get_date_range_worktime(self, start: date, end: date) -> list:
        """获取日期范围内的工时记录。"""
        return self._worktime_repo.get_range(start, end)

    def get_all_holidays(self) -> list:
        """获取全部节假日缓存。"""
        return self._holiday_repo.get_all()
