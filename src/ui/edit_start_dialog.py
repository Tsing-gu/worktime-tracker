# -*- coding: utf-8 -*-
"""
edit_start_dialog - 修改上班时间弹窗
====================================

提供手动输入或从 pmset 读取上班时间的界面。

版本: 0.13.0
"""

from PySide6 import QtWidgets, QtCore


class EditStartDialog(QtWidgets.QDialog):
    """修改上班时间对话框。"""

    def __init__(self, current_start_str: str, service, parent=None):
        """
        Args:
            current_start_str: 当前上班时间字符串 "HH:MM"（无记录时为空串）
            service:           WorktimeService 实例（用于读取 pmset）
            parent:            父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("修改上班时间")
        self.setMinimumWidth(280)
        self._service = service

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("今日上班时间 (HH:MM)："))

        self.input_edit = QtWidgets.QLineEdit(current_start_str)
        self.input_edit.setPlaceholderText("09:30")
        self.input_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        layout.addWidget(self.input_edit)

        pmset_btn = QtWidgets.QPushButton("从 pmset 读取")
        pmset_btn.clicked.connect(self._on_fill_pmset)
        layout.addWidget(pmset_btn)

        pmset_btn.setFocusPolicy(QtCore.Qt.NoFocus)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setFocusPolicy(QtCore.Qt.NoFocus)
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setAutoDefault(False)
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setFocusPolicy(QtCore.Qt.NoFocus)
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setAutoDefault(False)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_fill_pmset(self):
        """从 pmset 读取上班时间并填充输入框。"""
        pmset_time = self._service.get_pmset_start_time()
        if pmset_time:
            self.input_edit.setText(pmset_time.strftime("%H:%M"))
        else:
            QtWidgets.QMessageBox.information(self, "pmset", "未找到今天的活动记录")

    def get_time_str(self) -> str:
        """返回用户输入的时间字符串。"""
        return self.input_edit.text().strip()
