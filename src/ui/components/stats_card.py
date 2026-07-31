"""周期统计卡片。"""

from __future__ import annotations

from PySide6 import QtWidgets

from src.data.models import PeriodStats
from src.ui.theme import set_progress_state


class StatsCard(QtWidgets.QFrame):
    """展示一个周期的工作日、工时和目标进度。"""

    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(16, 16, 16, 16)

        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("CardTitle")
        layout.addWidget(title_label)
        divider = QtWidgets.QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(2)

        self.line1 = self._make_line(layout)
        self.line2 = self._make_line(layout)
        self.line3 = self._make_line(layout)
        layout.addSpacing(4)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setObjectName("CardBar")
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

    @staticmethod
    def _make_line(layout: QtWidgets.QVBoxLayout) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel("")
        label.setObjectName("CardLine")
        layout.addWidget(label)
        return label

    def update_stats(self, stats: PeriodStats) -> None:
        """用周期统计结果刷新卡片。"""
        if stats.is_rest:
            self.line1.setText("休息中")
            self.line2.clear()
            self.line3.clear()
            set_progress_state(self.progress_bar, 0, 0)
            return

        self.line1.setText(f"已工作 {stats.worked_days}天 / {stats.total_workdays}天")
        self.line2.setText(f"累计 {stats.worked_hours:.1f}h / 目标 {stats.target_hours:.0f}h")
        if stats.remaining_days > 1:
            self.line3.setText(
                f"日均 {stats.daily_avg:.1f}h, 剩余{stats.remaining_days}天 "
                f"每天需{stats.remaining_per_day:.1f}h达标"
            )
        else:
            left = max(0, stats.target_hours - stats.worked_hours)
            self.line3.setText(f"今天干完就放假啦！还剩{left:.1f}h")

        set_progress_state(self.progress_bar, stats.worked_hours, stats.target_hours)
