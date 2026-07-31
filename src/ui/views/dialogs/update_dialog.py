"""
update_dialog - 更新确认与下载进度弹窗
========================================

两个对话框:
    - UpdateConfirmDialog: 发现新版本时弹出，显示版本号/说明，用户确认是否更新
    - UpdateProgressDialog: 下载进度条，下载完成后提示重启

版本: 0.5.3
"""

import threading
from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from src.ui.components.dialog_buttons import make_dialog_button
from src.ui.theme.metrics import DIALOG_BOTTOM_MARGIN, DIALOG_MARGIN, MEDIUM_DIALOG_WIDTH
from src.utils.version import get_version


class UpdateConfirmDialogUI(QtWidgets.QDialog):
    """发现新版本时的确认弹窗。"""

    def __init__(self, info: object, parent: QtWidgets.QWidget | None = None) -> None:
        """
        Args:
            info: UpdateInfo 对象
        """
        super().__init__(parent)
        self.setWindowTitle("发现新版本")
        self.setMinimumWidth(MEDIUM_DIALOG_WIDTH)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(DIALOG_MARGIN, 20, DIALOG_MARGIN, DIALOG_BOTTOM_MARGIN)
        layout.setSpacing(12)

        title = QtWidgets.QLabel(f"新版本 {info.short_version} 可用")
        title.setObjectName("UpdateTitle")
        layout.addWidget(title)

        cur_label = QtWidgets.QLabel(f"当前版本：{get_version()}")
        cur_label.setObjectName("UpdateCur")
        layout.addWidget(cur_label)

        if info.description:
            desc = QtWidgets.QLabel(info.description)
            desc.setObjectName("UpdateDesc")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        # ── 立即更新/稍后按钮（手动创建两个实例，避免 QDialogButtonBox 焦点链问题）──
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        later_btn = make_dialog_button("稍后", "secondary", self.reject)
        update_btn = make_dialog_button("立即更新", "primary", self.accept)
        btn_layout.addWidget(later_btn)
        btn_layout.addWidget(update_btn)
        layout.addLayout(btn_layout)


class UpdateProgressDialogUI(QtWidgets.QDialog):
    """下载进度对话框。"""

    download_finished = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("正在下载更新")
        self.setMinimumWidth(MEDIUM_DIALOG_WIDTH)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(DIALOG_MARGIN, 20, DIALOG_MARGIN, DIALOG_BOTTOM_MARGIN)
        layout.setSpacing(12)

        self._status_label = QtWidgets.QLabel("正在下载更新包...")
        self._status_label.setObjectName("DlStatus")
        layout.addWidget(self._status_label)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setTextVisible(True)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        self._detail_label = QtWidgets.QLabel("")
        self._detail_label.setObjectName("DlDetail")
        layout.addWidget(self._detail_label)

        self._cancel_btn = make_dialog_button("取消下载", "danger", self._on_cancel)
        layout.addWidget(self._cancel_btn)

        self._cancelled = threading.Event()
        self._cancel_callback = None

    def _on_cancel(self) -> None:
        """用户点击取消下载。"""
        self._cancelled.set()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("正在取消...")
        self.set_status("正在取消下载...")
        if self._cancel_callback:
            self._cancel_callback()

    def is_cancelled(self) -> bool:
        """返回取消状态，可安全地由下载线程读取。"""
        return self._cancelled.is_set()

    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        """设置取消下载时的回调（用于通知 service 停止下载）。"""
        self._cancel_callback = callback

    def set_downloading(self) -> None:
        """下载开始后隐藏取消按钮的禁用状态。"""
        self._cancel_btn.setEnabled(True)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """关闭对话框时标记为取消并通知 service。"""
        if not self._cancelled.is_set():
            self._cancelled.set()
            if self._cancel_callback:
                self._cancel_callback()
        super().closeEvent(event)

    @QtCore.Slot(int, int)
    def update_progress(self, downloaded: int, total: int) -> None:
        """更新进度条。"""
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._bar.setValue(pct)
            dl_mb = downloaded / 1024 / 1024
            total_mb = total / 1024 / 1024
            self._detail_label.setText(f"{dl_mb:.1f} MB / {total_mb:.1f} MB")
        else:
            dl_mb = downloaded / 1024 / 1024
            self._detail_label.setText(f"{dl_mb:.1f} MB 已下载")

    @QtCore.Slot(str)
    def set_status(self, text: str) -> None:
        self._status_label.setText(text)
