"""更新检查流程的并发状态测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets

from src.ui.update_flow_controller import UpdateFlowController

pytestmark = pytest.mark.gui


@pytest.fixture
def controller(qtbot) -> UpdateFlowController:
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    factory = MagicMock()
    factory.update_service = MagicMock()
    factory.record_service = MagicMock()
    dialogs = MagicMock()
    return UpdateFlowController(parent, factory, dialogs)


def test_auto_check_is_blocked_while_manual_check_is_running(
    controller: UpdateFlowController,
) -> None:
    controller._update_checking = True

    controller.check_update_after_confirm()

    assert controller._update_checking is True


def test_any_check_result_clears_checking_state(controller: UpdateFlowController) -> None:
    controller._update_checking = True

    controller._on_update_check_finished(("auto", "error"))

    assert controller._update_checking is False
