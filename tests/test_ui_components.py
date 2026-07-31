"""可复用 UI 组件测试。"""

import pytest

from src.data.models import PeriodStats
from src.ui.components import ProgressCard, StatsCard, TodayStatusCard

pytestmark = pytest.mark.gui


def test_progress_card_updates_display(qtbot) -> None:
    card = ProgressCard()
    qtbot.addWidget(card)
    card.set_progress(4.0, 8.0)

    assert card.progress_bar.value() == 50
    assert "50%" in card.progress_label.text()


def test_stats_card_handles_rest_day(qtbot) -> None:
    card = StatsCard("本期概览")
    qtbot.addWidget(card)
    card.update_stats(PeriodStats(is_rest=True))

    assert card.line1.text() == "休息中"
    assert card.progress_bar.value() == 0


def test_today_status_card_emits_actions(qtbot) -> None:
    card = TodayStatusCard()
    qtbot.addWidget(card)
    edit_calls: list[bool] = []
    off_calls: list[bool] = []
    card.edit_start_requested.connect(lambda: edit_calls.append(True))
    card.manual_off_requested.connect(lambda: off_calls.append(True))

    card.edit_start_button.click()
    card.manual_off_button.click()

    assert edit_calls == [True]
    assert off_calls == [True]


def test_update_progress_dialog_cancel_state_is_thread_safe(qtbot) -> None:
    from src.ui.views.dialogs.update_dialog import UpdateProgressDialogUI

    dialog = UpdateProgressDialogUI()
    qtbot.addWidget(dialog)
    assert not dialog.is_cancelled()

    dialog._cancelled.set()

    assert dialog.is_cancelled()
