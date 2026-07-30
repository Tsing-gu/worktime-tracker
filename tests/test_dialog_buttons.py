"""
test_dialog_buttons - 对话框按钮封装单元测试
=============================================

覆盖 src/ui/dialog_buttons.py：
- make_dialog_button: 单按钮创建与配置
- make_ok_cancel_buttons: OK/Cancel 按钮对布局

用 pytest-qt 的 qtbot fixture 验证 QPushButton 行为。
"""

from __future__ import annotations

from PySide6 import QtWidgets

from src.ui.dialog_buttons import make_dialog_button, make_ok_cancel_buttons


class TestMakeDialogButton:
    """make_dialog_button：单按钮创建。"""

    def test_primary_button_config(self, qtbot) -> None:
        """primary 按钮配置正确。"""
        clicked = []
        btn = make_dialog_button("确定", "primary", lambda: clicked.append(1))
        qtbot.addWidget(btn)

        assert btn.text() == "确定"
        assert btn.objectName() == "PrimaryBtn"
        assert btn.focusPolicy() == __import__("PySide6").QtCore.Qt.StrongFocus
        assert btn.autoDefault() is False
        assert btn.isDefault() is False
        assert btn.minimumHeight() == 32 or btn.maximumHeight() == 32

    def test_secondary_button_config(self, qtbot) -> None:
        """secondary 按钮配置正确。"""
        btn = make_dialog_button("取消", "secondary", lambda: None)
        qtbot.addWidget(btn)

        assert btn.text() == "取消"
        assert btn.objectName() == "SecondaryBtn"

    def test_clicked_triggers_slot(self, qtbot) -> None:
        """点击按钮触发回调。"""
        clicked = []
        btn = make_dialog_button("确定", "primary", lambda: clicked.append(1))
        qtbot.addWidget(btn)

        btn.click()
        assert clicked == [1]

    def test_fixed_height_32(self, qtbot) -> None:
        """按钮固定高度 32。"""
        btn = make_dialog_button("确定", "primary", lambda: None)
        qtbot.addWidget(btn)
        assert btn.minimumHeight() == 32
        assert btn.maximumHeight() == 32


class TestMakeOkCancelButtons:
    """make_ok_cancel_buttons：OK/Cancel 按钮对布局。"""

    def test_layout_contains_two_buttons(self, qtbot) -> None:
        """布局包含 2 个按钮（取消 + 确定）+ 1 个 stretch。"""
        layout = make_ok_cancel_buttons("确定", "取消", lambda: None, lambda: None)
        # QHBoxLayout 的 count() 包含 stretch item
        assert layout.count() == 3  # 1 stretch + 2 button

    def test_cancel_button_on_left(self, qtbot) -> None:
        """取消按钮在左，确定按钮在右。"""
        ok_clicked = []
        cancel_clicked = []
        layout = make_ok_cancel_buttons(
            "确定", "取消", lambda: ok_clicked.append(1), lambda: cancel_clicked.append(1)
        )

        # 第 1 项是 stretch，第 2 项是 cancel_btn，第 3 项是 ok_btn
        cancel_item = layout.itemAt(1)
        ok_item = layout.itemAt(2)
        assert cancel_item is not None
        assert ok_item is not None
        cancel_btn = cancel_item.widget()
        ok_btn = ok_item.widget()
        assert isinstance(cancel_btn, QtWidgets.QPushButton)
        assert isinstance(ok_btn, QtWidgets.QPushButton)

        assert cancel_btn.text() == "取消"
        assert cancel_btn.objectName() == "SecondaryBtn"
        assert ok_btn.text() == "确定"
        assert ok_btn.objectName() == "PrimaryBtn"

    def test_ok_click_triggers_on_ok(self, qtbot) -> None:
        """点确定按钮触发 on_ok 回调。"""
        ok_clicked = []
        layout = make_ok_cancel_buttons(on_ok=lambda: ok_clicked.append(1), on_cancel=lambda: None)
        ok_item = layout.itemAt(2)
        assert ok_item is not None
        ok_btn = ok_item.widget()
        assert isinstance(ok_btn, QtWidgets.QPushButton)
        ok_btn.click()
        assert ok_clicked == [1]

    def test_cancel_click_triggers_on_cancel(self, qtbot) -> None:
        """点取消按钮触发 on_cancel 回调。"""
        cancel_clicked = []
        layout = make_ok_cancel_buttons(
            on_ok=lambda: None, on_cancel=lambda: cancel_clicked.append(1)
        )
        cancel_item = layout.itemAt(1)
        assert cancel_item is not None
        cancel_btn = cancel_item.widget()
        assert isinstance(cancel_btn, QtWidgets.QPushButton)
        cancel_btn.click()
        assert cancel_clicked == [1]

    def test_default_text(self, qtbot) -> None:
        """默认按钮文字是「确定」/「取消」。"""
        layout = make_ok_cancel_buttons()
        cancel_item = layout.itemAt(1)
        ok_item = layout.itemAt(2)
        assert cancel_item is not None and ok_item is not None
        cancel_btn = cancel_item.widget()
        ok_btn = ok_item.widget()
        assert isinstance(cancel_btn, QtWidgets.QPushButton)
        assert isinstance(ok_btn, QtWidgets.QPushButton)
        assert ok_btn.text() == "确定"
        assert cancel_btn.text() == "取消"

    def test_none_callbacks_dont_crash(self, qtbot) -> None:
        """on_ok/on_cancel 为 None 时点击不崩溃。"""
        layout = make_ok_cancel_buttons()
        ok_item = layout.itemAt(2)
        cancel_item = layout.itemAt(1)
        assert ok_item is not None and cancel_item is not None
        ok_btn = ok_item.widget()
        cancel_btn = cancel_item.widget()
        assert isinstance(ok_btn, QtWidgets.QPushButton)
        assert isinstance(cancel_btn, QtWidgets.QPushButton)
        # 不应抛异常
        ok_btn.click()
        cancel_btn.click()
