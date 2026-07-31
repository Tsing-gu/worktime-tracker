"""主题系统与动态状态样式测试。"""

import pytest
from PySide6 import QtWidgets

from src.ui.theme import build_qss, get_theme, set_progress_state

pytestmark = pytest.mark.gui


def test_theme_qss_contains_shared_state_rules(qapp: QtWidgets.QApplication) -> None:
    qss = build_qss(get_theme())

    assert 'QProgressBar[progress-state="complete"]::chunk' in qss
    assert 'QFrame#DayCell[day-state="leave"]' in qss
    assert 'QLabel#OfficeDomain[state="configured"]' in qss
    assert "QMenu#TrayPopup" in qss


def test_progress_state_uses_dynamic_property(qtbot) -> None:
    bar = QtWidgets.QProgressBar()
    qtbot.addWidget(bar)

    set_progress_state(bar, 8.0, 8.0)
    assert bar.property("progress-state") == "complete"
    assert bar.value() == 100

    set_progress_state(bar, 0.0, 0.0)
    assert bar.property("progress-state") == "empty"
    assert bar.value() == 0
