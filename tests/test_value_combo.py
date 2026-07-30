"""
test_value_combo - 数值下拉列表单元测试
=======================================

覆盖 src/ui/value_combo.py 的 ValueComboBox：
- 整数范围生成选项数
- 固定 3 项（离开等待时长 60/120/180）
- suffix 显示 / get_value 去后缀
- set_value 匹配已存在项 / 追加非标准值
- decimals 控制小数位
- 初始选中首项

用 pytest-qt 的 qtbot fixture 验证 QComboBox 行为。
"""

from __future__ import annotations

from src.ui.value_combo import ValueComboBox


class TestValueComboBox:
    """ValueComboBox：数值下拉列表。"""

    def test_int_range_1_to_7_has_7_items(self, qtbot) -> None:
        """整数范围 1~7 → 7 项。"""
        combo = ValueComboBox(start=1, stop=7, step=1, decimals=0, suffix=" 天")
        qtbot.addWidget(combo)
        assert combo.count() == 7
        assert combo.itemText(0) == "1 天"
        assert combo.itemText(6) == "7 天"

    def test_off_threshold_has_3_items(self, qtbot) -> None:
        """离开等待时长 60~180 步进 60 → 3 项（60/120/180 分钟）。"""
        combo = ValueComboBox(start=60, stop=180, step=60, decimals=0, suffix=" 分钟")
        qtbot.addWidget(combo)
        assert combo.count() == 3
        assert combo.itemText(0) == "60 分钟"
        assert combo.itemText(1) == "120 分钟"
        assert combo.itemText(2) == "180 分钟"

    def test_suffix_displayed(self, qtbot) -> None:
        """suffix 显示在选项文本中。"""
        combo = ValueComboBox(start=1, stop=3, step=1, decimals=0, suffix=" 天")
        qtbot.addWidget(combo)
        for i in range(combo.count()):
            assert combo.itemText(i).endswith(" 天")

    def test_get_value_no_suffix(self, qtbot) -> None:
        """get_value 返回值不带 suffix。"""
        combo = ValueComboBox(start=60, stop=180, step=60, decimals=0, suffix=" 分钟")
        qtbot.addWidget(combo)
        combo.set_value(120)
        assert combo.get_value() == "120"  # 不含 " 分钟"

    def test_set_value_matches_existing_int(self, qtbot) -> None:
        """set_value 命中已存在整数项 → 选中，不新增。"""
        combo = ValueComboBox(start=1, stop=7, step=1, decimals=0, suffix=" 天")
        qtbot.addWidget(combo)
        combo.set_value(5)
        assert combo.currentText() == "5 天"
        assert combo.count() == 7  # 未新增

    def test_set_value_appends_non_standard(self, qtbot) -> None:
        """set_value 未命中（90 不在 60/120/180 中）→ 追加并选中。"""
        combo = ValueComboBox(start=60, stop=180, step=60, decimals=0, suffix=" 分钟")
        qtbot.addWidget(combo)
        combo.set_value(90)
        assert combo.count() == 4  # 追加 1 项
        assert combo.currentText() == "90 分钟"

    def test_get_value_int_no_decimals(self, qtbot) -> None:
        """decimals=0 → 返回整数格式字符串。"""
        combo = ValueComboBox(start=1, stop=7, step=1, decimals=0)
        qtbot.addWidget(combo)
        combo.set_value(5)
        assert combo.get_value() == "5"

    def test_initial_selection_is_first(self, qtbot) -> None:
        """初始选中首项。"""
        combo = ValueComboBox(start=60, stop=180, step=60, decimals=0, suffix=" 分钟")
        qtbot.addWidget(combo)
        assert combo.currentIndex() == 0
        assert combo.get_value() == "60"
