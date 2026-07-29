"""
stats_service - 工时统计服务
============================

负责今日状态、本期统计、本月统计的查询。
从原 WorktimeService 拆分而来，只管统计查询。

计算器缓存由本类管理，设置变更时通过 SettingsService.register_on_changed 失效。

版本: 0.16.0
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.core.calculator import WorktimeCalculatorCore
from src.data.holiday_repo import HolidayRepository
from src.data.models import PeriodStats, TodayStatus
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.settings_service import SettingsService
from src.utils.date_utils import compute_work_date, get_month_range, get_period_range

logger = logging.getLogger(__name__)


class StatsService:
    """工时统计服务。

    依赖通过构造期注入：
        - worktime_repo:    DailyWorktimeRepository
        - holiday_repo:     HolidayRepository
        - settings_service: SettingsService（类型化设置）
    """

    def __init__(
        self,
        worktime_repo: DailyWorktimeRepository,
        holiday_repo: HolidayRepository,
        settings_service: SettingsService,
    ) -> None:
        self._worktime_repo = worktime_repo
        self._holiday_repo = holiday_repo
        self._settings = settings_service
        self._calculator: WorktimeCalculatorCore | None = None
        # 注册设置变更回调，设置变了就失效计算器缓存
        self._settings.register_on_changed(self.invalidate_calculator)

    def get_today_status(self) -> TodayStatus:
        """获取今日实时工时状态。"""
        today = compute_work_date(datetime.now())
        daily = self._worktime_repo.get(today)
        return self._get_calculator().today_status(today, daily, now=datetime.now())

    def get_period_stats(self) -> PeriodStats:
        """获取本期工时统计。"""
        today = compute_work_date(datetime.now())
        calc = self._get_calculator()
        holidays = self._holiday_repo.get_all()
        period = get_period_range(today, holidays, calc.weekly_work_days)
        if period is None:
            return PeriodStats(is_rest=True)
        period_start, period_end = period
        records = self._worktime_repo.get_range(period_start, period_end)
        return calc.period_stats(today, records, now=datetime.now(), period=period)

    def get_month_stats(self) -> PeriodStats:
        """获取本月工时统计。"""
        today = compute_work_date(datetime.now())
        month_start, month_end = get_month_range(today)
        records = self._worktime_repo.get_range(month_start, month_end)
        return self._get_calculator().month_stats(today, records, now=datetime.now())

    def get_required_hours(self) -> float:
        """获取每日工时要求。"""
        return self._settings.get().daily_required_hours

    def get_calculator(self) -> WorktimeCalculatorCore:
        """获取计算器实例（供 RecordService 等使用）。"""
        return self._get_calculator()

    def invalidate_calculator(self) -> None:
        """失效计算器缓存（设置变更时由回调触发）。"""
        self._calculator = None
        logger.debug("计算器缓存已失效")

    def _get_calculator(self) -> WorktimeCalculatorCore:
        """懒加载计算器，从 Settings + holidays 构建。"""
        if self._calculator is None:
            holidays = self._holiday_repo.get_all()
            settings = self._settings.get()
            self._calculator = WorktimeCalculatorCore(
                holidays=holidays,
                daily_required=settings.daily_required_hours,
                holiday_auto_exclude=settings.holiday_auto_exclude,
                weekly_work_days=settings.weekly_work_days,
            )
        return self._calculator
