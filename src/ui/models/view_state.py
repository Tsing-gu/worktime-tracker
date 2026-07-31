"""面向 UI 的展示状态，不承载数据库或业务规则。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.data.models import TodayStatus


@dataclass(frozen=True)
class DashboardViewState:
    """主窗口今日状态的展示快照。"""

    worked_hours: float
    required_hours: float
    progress_percent: int
    start_text: str
    eta_text: str
    is_target_reached: bool
    is_off_work: bool


def build_dashboard_view_state(status: TodayStatus, now: datetime) -> DashboardViewState:
    """把 Service 返回的 TodayStatus 转为 UI 可直接展示的状态。"""
    required = status.required_hours
    progress_percent = int(status.worked_hours / required * 100) if required > 0 else 0

    if status.start_time:
        start_text = status.start_time.strftime("%H:%M")
    else:
        start_text = "--:--"

    if status.start_time and not status.end_time:
        remaining = max(0, required - status.worked_hours)
        eta_text = (now + timedelta(hours=remaining)).strftime("%H:%M")
    elif status.end_time:
        eta_text = "已下班"
    else:
        eta_text = "--:--"

    return DashboardViewState(
        worked_hours=status.worked_hours,
        required_hours=required,
        progress_percent=progress_percent,
        start_text=start_text,
        eta_text=eta_text,
        is_target_reached=status.is_target_reached,
        is_off_work=status.end_time is not None,
    )
