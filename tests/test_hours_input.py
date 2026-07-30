"""
test_hours_input - 工时输入框单元测试
=====================================

覆盖 src/ui/hours_input.py 的 HoursInput：
- set_value 填充初始值
- get_value 返回字符串格式
- get_value 空值/非法返回默认 8.0
- get_value 去尾零（8.50 → "8.5"）

用 pytest-qt 的 qtbot fixture 验证 QLineEdit 行为。
"""

from __future__ import annotations

from src.ui.hours_input import HoursInput


class TestHoursInput:
    """HoursInput：工时输入框（0~24，xx.xx，纯数字存储）。"""

    def test_set_value_fills_text(self, qtbot) -> None:
        """set_value 填充初始值到输入框。"""
        inp = HoursInput()
        qtbot.addWidget(inp)
        inp.set_value("8.0")
        assert inp.text() == "8"

    def test_get_value_returns_string(self, qtbot) -> None:
        """get_value 返回字符串格式。"""
        inp = HoursInput()
        qtbot.addWidget(inp)
        inp.setText("8.5")
        assert inp.get_value() == "8.5"

    def test_get_value_empty_returns_default(self, qtbot) -> None:
        """空输入 → 返回默认值 "8.0"。"""
        inp = HoursInput()
        qtbot.addWidget(inp)
        inp.setText("")
        assert inp.get_value() == "8"

    def test_get_value_invalid_returns_default(self, qtbot) -> None:
        """非法输入 → 返回默认值（QDoubleValidator 拦截，兜底）。"""
        inp = HoursInput()
        qtbot.addWidget(inp)
        # 绕过 validator 直接 setText 非法值（模拟兜底逻辑）
        inp.setText("abc")
        assert inp.get_value() == "8"

    def test_get_value_trailing_zeros(self, qtbot) -> None:
        """输入 8.50 → 返回 "8.5"（去尾零）。"""
        inp = HoursInput()
        qtbot.addWidget(inp)
        inp.setText("8.50")
        assert inp.get_value() == "8.5"
