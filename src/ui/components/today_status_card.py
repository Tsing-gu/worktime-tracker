"""今日工时状态卡片。"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from src.ui.components.progress_card import ProgressCard
from src.ui.dialog_buttons import make_dialog_button


class TodayStatusCard(QtWidgets.QFrame):
    """展示今日上下班状态，并通过信号暴露用户操作。"""

    edit_start_requested = QtCore.Signal()
    manual_off_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(12)
        self.edit_start_button = make_dialog_button(
            "修改上班", "secondary", self.edit_start_requested.emit
        )
        self.manual_off_button = make_dialog_button(
            "手动下班", "primary", self.manual_off_requested.emit
        )
        buttons.addWidget(self.edit_start_button)
        buttons.addStretch()
        buttons.addWidget(self.manual_off_button)
        layout.addLayout(buttons)

        info = QtWidgets.QHBoxLayout()
        info.setSpacing(24)
        self.start_label = self._make_value_column(info, "--:--", "上班时间")
        info.addStretch()
        self.worked_label = self._make_value_column(info, "0.0h", "当前已工作")
        info.addStretch()
        self.eta_label = self._make_value_column(info, "--:--", "预计下班")
        layout.addLayout(info)

        self.progress_card = ProgressCard()
        layout.addWidget(self.progress_card)

    @staticmethod
    def _make_value_column(
        parent_layout: QtWidgets.QHBoxLayout, value: str, subtitle: str
    ) -> QtWidgets.QLabel:
        column = QtWidgets.QVBoxLayout()
        column.setSpacing(2)
        value_label = QtWidgets.QLabel(value)
        value_label.setObjectName("WorkedValue")
        value_label.setAlignment(QtCore.Qt.AlignCenter)
        column.addWidget(value_label)
        subtitle_label = QtWidgets.QLabel(subtitle)
        subtitle_label.setObjectName("WorkedSub")
        subtitle_label.setAlignment(QtCore.Qt.AlignCenter)
        column.addWidget(subtitle_label)
        parent_layout.addLayout(column)
        return value_label

    def update_state(
        self,
        *,
        start_text: str,
        worked_hours: float,
        eta_text: str,
        required_hours: float,
    ) -> None:
        """更新卡片展示状态。"""
        self.start_label.setText(start_text)
        self.worked_label.setText(f"{worked_hours:.1f}h")
        self.eta_label.setText(eta_text)
        self.progress_card.set_progress(worked_hours, required_hours)
