"""
value_combo - 数值下拉列表
==========================

生成 [start, stop] 范围内按 step 步进的数值选项，
适配 DB 中存储的字符串格式。提供输入校验：
set_value 匹配失败时追加（兼容历史值）。

版本: 0.16.5
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class ValueComboBox(QtWidgets.QComboBox):
    """数值下拉列表，适配 DB 中存储的字符串格式。

    生成 [start, stop] 范围内按 step 步进的数值选项，
    提供输入校验：``set_value`` 匹配失败时追加（兼容历史值），
    ``get_value`` 返回字符串格式（与 DB 存储一致）。

    Args:
        start:    起始值（含）
        stop:     结束值（含）
        step:     步进
        decimals: 小数位数（0=整数，1=一位小数）
        suffix:   显示单位后缀（如 " 分钟"），get_value 返回时不带
        parent:   父控件
    """

    def __init__(
        self,
        start: float,
        stop: float,
        step: float = 1.0,
        decimals: int = 0,
        suffix: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._decimals = decimals
        self._suffix = suffix
        self._fmt = f"{{:.{decimals}f}}"
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._populate(start, stop, step)

    def _populate(self, start: float, stop: float, step: float) -> None:
        """填充 start ~ stop 按 step 步进的选项。"""
        # 用整数计数避免浮点累计误差（如 0.5 步进）
        steps = int(round((stop - start) / step))
        for i in range(steps + 1):
            value = start + i * step
            self.addItem(self._fmt.format(value) + self._suffix)

    def set_value(self, value: float | int | str) -> None:
        """设置当前值。

        匹配失败（非标准值，如 90 不在 60/120/180 中）时追加到列表末尾，
        保证老用户历史设置值不丢失。

        Args:
            value: 数值（float/int）或字符串
        """
        if isinstance(value, str):
            text = value + self._suffix
            idx = self.findText(text)
            if idx < 0:
                # 字符串可能是纯数字，也可能是带 suffix 的显示文本
                idx = self.findText(value)
            if idx < 0:
                # 尝试解析为 float 再格式化
                try:
                    text = self._fmt.format(float(value)) + self._suffix
                    idx = self.findText(text)
                except ValueError:
                    pass
            if idx >= 0:
                self.setCurrentIndex(idx)
            else:
                self.addItem(text)
                self.setCurrentIndex(self.count() - 1)
        else:
            text = self._fmt.format(float(value)) + self._suffix
            idx = self.findText(text)
            if idx >= 0:
                self.setCurrentIndex(idx)
            else:
                self.addItem(text)
                self.setCurrentIndex(self.count() - 1)

    def get_value(self) -> str:
        """返回当前选中值（字符串格式，不带 suffix）。"""
        text = self.currentText()
        if self._suffix and text.endswith(self._suffix):
            text = text[: -len(self._suffix)]
        return text
