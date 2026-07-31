"""
test_dialog_buttons - 对话框按钮封装单元测试
=============================================

覆盖 src/ui/components/dialog_buttons.py 的 make_dialog_button：
- primary / secondary / danger 三种角色配置正确
- 点击触发回调
- fixed_height / fixed_size 参数生效

用 pytest-qt 的 qtbot fixture 验证 QPushButton 行为。
"""

from __future__ import annotations

import pytest
from PySide6 import QtCore

from src.ui.components.dialog_buttons import make_dialog_button

pytestmark = pytest.mark.gui


class TestMakeDialogButton:
    """make_dialog_button：单按钮创建与配置。"""

    def test_primary_button_config(self, qtbot) -> None:
        """primary 按钮配置正确。"""
        clicked = []
        btn = make_dialog_button("确定", "primary", lambda: clicked.append(1))
        qtbot.addWidget(btn)

        assert btn.text() == "确定"
        assert btn.objectName() == "PrimaryBtn"
        assert btn.focusPolicy() == QtCore.Qt.StrongFocus
        assert btn.autoDefault() is False
        assert btn.isDefault() is False

    def test_secondary_button_config(self, qtbot) -> None:
        """secondary 按钮配置正确。"""
        btn = make_dialog_button("取消", "secondary", lambda: None)
        qtbot.addWidget(btn)

        assert btn.text() == "取消"
        assert btn.objectName() == "SecondaryBtn"

    def test_danger_button_config(self, qtbot) -> None:
        """danger 按钮配置正确（用于取消下载等危险操作）。"""
        btn = make_dialog_button("取消下载", "danger", lambda: None)
        qtbot.addWidget(btn)

        assert btn.text() == "取消下载"
        assert btn.objectName() == "DangerBtn"

    def test_clicked_triggers_slot(self, qtbot) -> None:
        """点击按钮触发回调。"""
        clicked = []
        btn = make_dialog_button("确定", "primary", lambda: clicked.append(1))
        qtbot.addWidget(btn)

        btn.click()
        assert clicked == [1]

    def test_default_fixed_height_32(self, qtbot) -> None:
        """默认固定高度 32。"""
        btn = make_dialog_button("确定", "primary", lambda: None)
        qtbot.addWidget(btn)
        assert btn.minimumHeight() == 32
        assert btn.maximumHeight() == 32

    def test_custom_fixed_height(self, qtbot) -> None:
        """自定义 fixed_height。"""
        btn = make_dialog_button("确定", "primary", lambda: None, fixed_height=40)
        qtbot.addWidget(btn)
        assert btn.minimumHeight() == 40
        assert btn.maximumHeight() == 40

    def test_fixed_size_overrides_height(self, qtbot) -> None:
        """fixed_size 优先于 fixed_height。"""
        btn = make_dialog_button("◀", "secondary", lambda: None, fixed_size=(44, 32))
        qtbot.addWidget(btn)
        assert btn.minimumWidth() == 44
        assert btn.maximumWidth() == 44
        assert btn.minimumHeight() == 32
        assert btn.maximumHeight() == 32

    def test_unknown_role_defaults_to_primary(self, qtbot) -> None:
        """未知 role 默认用 PrimaryBtn。"""
        btn = make_dialog_button("确定", "unknown_role", lambda: None)
        qtbot.addWidget(btn)
        assert btn.objectName() == "PrimaryBtn"

    def test_auto_default_always_false(self, qtbot) -> None:
        """所有按钮 autoDefault 始终为 False（修复 macOS 点击问题的关键）。"""
        for role in ("primary", "secondary", "danger"):
            btn = make_dialog_button("text", role, lambda: None)
            qtbot.addWidget(btn)
            assert btn.autoDefault() is False, f"role={role} autoDefault 应为 False"
            assert btn.isDefault() is False, f"role={role} default 应为 False"
