"""UI 展示状态模型测试。"""

from datetime import datetime

from src.data.models import TodayStatus
from src.ui.models import build_dashboard_view_state


def test_build_dashboard_view_state_for_active_workday() -> None:
    state = build_dashboard_view_state(
        TodayStatus(
            start_time=datetime(2026, 7, 31, 9, 0),
            worked_hours=4.0,
            required_hours=8.0,
        ),
        datetime(2026, 7, 31, 13, 0),
    )

    assert state.start_text == "09:00"
    assert state.progress_percent == 50
    assert state.eta_text == "17:00"
    assert not state.is_off_work


def test_build_dashboard_view_state_for_finished_workday() -> None:
    state = build_dashboard_view_state(
        TodayStatus(
            start_time=datetime(2026, 7, 31, 9, 0),
            end_time=datetime(2026, 7, 31, 18, 0),
            worked_hours=9.0,
            required_hours=8.0,
            is_target_reached=True,
        ),
        datetime(2026, 7, 31, 18, 30),
    )

    assert state.progress_percent == 112
    assert state.eta_text == "已下班"
    assert state.is_target_reached
    assert state.is_off_work
