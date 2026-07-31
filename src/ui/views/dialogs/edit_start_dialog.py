"""
edit_start_dialog - 修改上班时间弹窗
====================================

提供手动输入或从 pmset 读取上班时间的界面。

版本: 0.13.0
"""

from PySide6 import QtCore, QtWidgets

from src.app.runtime import start_managed_thread
from src.services.tracking_service import TrackingService
from src.ui.components.dialog_buttons import make_dialog_button
from src.ui.theme.metrics import SMALL_DIALOG_WIDTH


class EditStartDialogUI(QtWidgets.QDialog):
    """修改上班时间对话框。"""

    def __init__(
        self,
        current_start_str: str,
        service: TrackingService,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """
        Args:
            current_start_str: 当前上班时间字符串 "HH:MM"（无记录时为空串）
            service:           TrackingService 实例（用于读取 pmset）
            parent:            父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("修改上班时间")
        self.setMinimumWidth(SMALL_DIALOG_WIDTH)
        self._service = service

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("今日上班时间 (HH:MM)："))

        self.input_edit = QtWidgets.QLineEdit(current_start_str)
        self.input_edit.setPlaceholderText("09:30")
        self.input_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        layout.addWidget(self.input_edit)

        self._pmset_btn = make_dialog_button("从 pmset 读取", "secondary", self._on_fill_pmset)
        layout.addWidget(self._pmset_btn)

        # ── 确定/取消按钮（手动创建两个实例，避免 QDialogButtonBox 焦点链问题）──
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = make_dialog_button("取消", "secondary", self.reject)
        ok_btn = make_dialog_button("确定", "primary", self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _on_fill_pmset(self) -> None:
        """从 pmset 读取上班时间，子线程执行避免阻塞 UI。"""
        self._pmset_btn.setEnabled(False)
        self._pmset_btn.setText("读取中...")

        def worker() -> None:
            pmset_time = self._service.get_pmset_start_time()
            time_str = pmset_time.strftime("%H:%M") if pmset_time else ""
            QtCore.QMetaObject.invokeMethod(
                self, "_on_pmset_result", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(str, time_str)
            )

        start_managed_thread(worker, name="pmset-start-time")

    @QtCore.Slot(str)
    def _on_pmset_result(self, time_str: str) -> None:
        """pmset 读取完成，在主线程回填输入框。"""
        self._pmset_btn.setEnabled(True)
        self._pmset_btn.setText("从 pmset 读取")
        if time_str:
            self.input_edit.setText(time_str)
        else:
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("pmset")
            dlg.setMinimumWidth(320)
            layout = QtWidgets.QVBoxLayout(dlg)
            layout.setContentsMargins(24, 20, 24, 16)
            layout.setSpacing(12)
            label = QtWidgets.QLabel("未找到今天的活动记录")
            label.setWordWrap(True)
            layout.addWidget(label)
            btn_layout = QtWidgets.QHBoxLayout()
            btn_layout.addStretch()
            ok_btn = make_dialog_button("确定", "primary", dlg.accept)
            btn_layout.addWidget(ok_btn)
            layout.addLayout(btn_layout)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def get_time_str(self) -> str:
        """返回用户输入的时间字符串。"""
        return self.input_edit.text().strip()
