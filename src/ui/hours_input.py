"""
hours_input - 工时输入框
========================

自由输入工时，QDoubleValidator 实时校验 0~24，
格式 xx.xx，纯数字存储（不带 h 后缀）。

版本: 0.16.5
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

# 解析失败时的默认值
_DEFAULT_HOURS = 8.0


class HoursInput(QtWidgets.QLineEdit):
    """工时输入框，校验 0~24，格式 xx.xx，纯数字存储。

    用 ``QDoubleValidator(0.0, 24.0, 2)`` 限制输入范围，
    ``get_value`` 返回纯数字字符串（不带 h 后缀，与 DB 存储格式一致）。

    Args:
        parent: 父控件
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("0~24，如 8.5")
        self.setValidator(QtGui.QDoubleValidator(0.0, 24.0, 2, self))
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

    def set_value(self, value: float | str) -> None:
        """填充初始值。

        Args:
            value: 数值（float）或字符串
        """
        try:
            f = float(value)
        except (TypeError, ValueError):
            f = _DEFAULT_HOURS
        # 去尾零：8.50 → "8.5"，8.00 → "8"
        text = f"{f:g}"
        self.setText(text)

    def get_value(self) -> str:
        """返回当前值（纯数字字符串）。

        空值或非法时返回默认值 "8"；合法时返回去尾零的字符串
        （如 8.50 → "8.5"，8.00 → "8"）。
        """
        text = self.text().strip()
        if not text:
            return f"{_DEFAULT_HOURS:g}"
        try:
            f = float(text)
        except ValueError:
            return f"{_DEFAULT_HOURS:g}"
        # 超范围 clamp 到 0~24
        f = max(0.0, min(24.0, f))
        return f"{f:g}"
