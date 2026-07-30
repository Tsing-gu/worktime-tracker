"""
test_time_combo - 24小时制时间下拉列表单元测试
=============================================

覆盖 src/ui/time_combo.py 的 TimeComboBox：
- 默认/自定义步进粒度生成选项数
- set_time 匹配已存在项 / 追加非标准项
- get_time 返回当前选中
- 初始选中首项

用 pytest-qt 的 qtbot fixture 验证 QComboBox 行为。
"""

from __future__ import annotations

from src.ui.time_combo import TimeComboBox


class TestTimeComboBox:
    """TimeComboBox：24小时制时间下拉。"""

    def test_default_step_30min_has_48_items(self, qtbot) -> None:
        """默认步进 30 分钟 → 48 项（00:00 ~ 23:30）。"""
        combo = TimeComboBox(step_minutes=30)
        qtbot.addWidget(combo)
        assert combo.count() == 48
        assert combo.itemText(0) == "00:00"
        assert combo.itemText(47) == "23:30"

    def test_custom_step_15min_has_96_items(self, qtbot) -> None:
        """自定义步进 15 分钟 → 96 项（00:00 ~ 23:45）。"""
        combo = TimeComboBox(step_minutes=15)
        qtbot.addWidget(combo)
        assert combo.count() == 96
        assert combo.itemText(0) == "00:00"
        assert combo.itemText(95) == "23:45"

    def test_custom_step_60min_has_24_items(self, qtbot) -> None:
        """自定义步进 60 分钟 → 24 项（00:00 ~ 23:00）。"""
        combo = TimeComboBox(step_minutes=60)
        qtbot.addWidget(combo)
        assert combo.count() == 24
        assert combo.itemText(0) == "00:00"
        assert combo.itemText(23) == "23:00"

    def test_set_time_matches_existing(self, qtbot) -> None:
        """set_time 命中已存在项 → 选中该项，不新增。"""
        combo = TimeComboBox(step_minutes=30)
        qtbot.addWidget(combo)
        combo.set_time("19:00")
        assert combo.currentIndex() == 38  # 19:00 = 19*2 = 第 38 项
        assert combo.count() == 48  # 未新增

    def test_set_time_appends_non_standard(self, qtbot) -> None:
        """set_time 未命中（非标准粒度 "19:15"）→ 追加到末尾并选中。"""
        combo = TimeComboBox(step_minutes=30)
        qtbot.addWidget(combo)
        combo.set_time("19:15")
        assert combo.count() == 49  # 追加 1 项
        assert combo.currentText() == "19:15"

    def test_get_time_returns_current(self, qtbot) -> None:
        """get_time 返回当前选中时间。"""
        combo = TimeComboBox(step_minutes=30)
        qtbot.addWidget(combo)
        combo.set_time("20:30")
        assert combo.get_time() == "20:30"

    def test_initial_selection_is_first(self, qtbot) -> None:
        """初始选中首项 "00:00"。"""
        combo = TimeComboBox(step_minutes=30)
        qtbot.addWidget(combo)
        assert combo.currentIndex() == 0
        assert combo.get_time() == "00:00"
