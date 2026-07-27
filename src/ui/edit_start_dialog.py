# -*- coding: utf-8 -*-
"""
edit_start_dialog - 修改上班时间弹窗
====================================

提供手动输入或从 pmset 读取上班时间的界面。

版本: 0.13.0
"""

import threading

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

        self._pmset_btn = QtWidgets.QPushButton("从 pmset 读取")
        self._pmset_btn.clicked.connect(self._on_fill_pmset)
        self._pmset_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        layout.addWidget(self._pmset_btn)

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
        """从 pmset 读取上班时间，子线程执行避免阻塞 UI。"""
        self._pmset_btn.setEnabled(False)
        self._pmset_btn.setText("读取中...")

        def worker():
            pmset_time = self._service.get_pmset_start_time()
            time_str = pmset_time.strftime("%H:%M") if pmset_time else ""
            QtCore.QMetaObject.invokeMethod(self, "_on_pmset_result",
                                            QtCore.Qt.QueuedConnection,
                                            QtCore.Q_ARG(str, time_str))

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(str)
    def _on_pmset_result(self, time_str):
        """pmset 读取完成，在主线程回填输入框。"""
        self._pmset_btn.setEnabled(True)
        self._pmset_btn.setText("从 pmset 读取")
        if time_str:
            self.input_edit.setText(time_str)
        else:
            box = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Information, "pmset",
                "未找到今天的活动记录", QtWidgets.QMessageBox.Ok, self)
            for btn in box.buttons():
                btn.setAutoDefault(False)
                btn.setFocusPolicy(QtCore.Qt.NoFocus)
            box.show()

    def get_time_str(self) -> str:
        """返回用户输入的时间字符串。"""
        return self.input_edit.text().strip()
