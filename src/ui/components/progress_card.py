"""今日目标进度组件。"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from src.ui.theme import set_progress_state


class ProgressCard(QtWidgets.QWidget):
    """封装进度文案和进度条，供未来动画进度组件替换。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.progress_label = QtWidgets.QLabel("今日目标 8.0h  0%")
        self.progress_label.setObjectName("SmallSec")
        self.progress_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.progress_label)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

    def set_progress(self, worked: float, required: float) -> None:
        """更新进度显示，不改变任何业务状态。"""
        percent = int(worked / required * 100) if required > 0 else 0
        self.progress_label.setText(f"今日目标 {required:.1f}h  {percent}%")
        set_progress_state(self.progress_bar, worked, required)
