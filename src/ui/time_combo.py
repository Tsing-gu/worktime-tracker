"""
time_combo - 24小时制时间下拉列表
=================================

固定 24 小时制显示，消除 macOS 系统区域设置导致 QTimeEdit
可能显示为 12 小时制的问题。适配 DB 中存储的 "HH:MM" 时间戳格式。

版本: 0.16.5
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class TimeComboBox(QtWidgets.QComboBox):
    """24小时制时间下拉列表（HH:MM 格式）。

    按 ``step_minutes`` 粒度生成 00:00 ~ 23:59 的选项，
    适配 DB 中存储的 "HH:MM" 时间戳格式，固定 24 小时制显示，
    不受 macOS 系统区域设置影响。

    Args:
        step_minutes: 选项粒度（分钟），默认 30 生成 48 项
        parent:      父控件
    """

    def __init__(self, step_minutes: int = 30, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._step_minutes = step_minutes
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._populate()

    def _populate(self) -> None:
        """填充 00:00 ~ 23:59 按 step_minutes 粒度的选项。"""
        for total_min in range(0, 24 * 60, self._step_minutes):
            h, m = divmod(total_min, 60)
            self.addItem(f"{h:02d}:{m:02d}")

    def set_time(self, time_str: str) -> None:
        """设置当前时间。

        匹配失败（非标准粒度，如 "19:15"）时追加到列表末尾，
        保证老用户历史设置值不丢失。

        Args:
            time_str: "HH:MM" 格式时间字符串
        """
        idx = self.findText(time_str)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.addItem(time_str)
            self.setCurrentIndex(self.count() - 1)

    def get_time(self) -> str:
        """返回当前选中时间（"HH:MM" 格式）。"""
        return self.currentText()
