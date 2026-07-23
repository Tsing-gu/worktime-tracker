# -*- coding: utf-8 -*-
"""
update_dialog - 更新确认与下载进度弹窗
========================================

两个对话框:
    - UpdateConfirmDialog: 发现新版本时弹出，显示版本号/说明，用户确认是否更新
    - UpdateProgressDialog: 下载进度条，下载完成后提示重启

版本: 0.5.3
"""

from PySide6 import QtWidgets, QtCore, QtGui

from src.ui.theme import get_theme


class UpdateConfirmDialog(QtWidgets.QDialog):
    """发现新版本时的确认弹窗。"""

    def __init__(self, info, parent=None):
        """
        Args:
            info: UpdateInfo 对象
        """
        super().__init__(parent)
        self.setWindowTitle("发现新版本")
        self.setMinimumWidth(380)

        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QLabel {{ color: {t['main']}; }}
            QCheckBox {{ color: {t['sec']}; }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QtWidgets.QLabel(f"新版本 {info.short_version} 可用")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {t['primary']};")
        layout.addWidget(title)

        cur_label = QtWidgets.QLabel(f"当前版本：{__import__('src.utils.version', fromlist=['get_version']).get_version()}")
        cur_label.setStyleSheet(f"font-size: 12px; color: {t['sec']};")
        layout.addWidget(cur_label)

        if info.description:
            desc = QtWidgets.QLabel(info.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"font-size: 13px; color: {t['main']};")
            layout.addWidget(desc)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Yes | QtWidgets.QDialogButtonBox.No
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Yes).setText("立即更新")
        btn_box.button(QtWidgets.QDialogButtonBox.No).setText("稍后")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)


class UpdateProgressDialog(QtWidgets.QDialog):
    """下载进度对话框。"""

    download_finished = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在下载更新")
        self.setMinimumWidth(360)
        self.setModal(True)

        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg']}; }}
            QLabel {{ color: {t['main']}; }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self._status_label = QtWidgets.QLabel("正在下载更新包...")
        self._status_label.setStyleSheet(f"font-size: 14px; color: {t['main']};")
        layout.addWidget(self._status_label)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setTextVisible(True)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        self._detail_label = QtWidgets.QLabel("")
        self._detail_label.setStyleSheet(f"font-size: 12px; color: {t['sec']};")
        layout.addWidget(self._detail_label)

        self._cancel_btn = QtWidgets.QPushButton("取消下载")
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn)

        self._cancelled = False
        self._cancel_callback = None

    def _on_cancel(self):
        """用户点击取消下载。"""
        self._cancelled = True
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("正在取消...")
        self.set_status("正在取消下载...")
        if self._cancel_callback:
            self._cancel_callback()

    def is_cancelled(self) -> bool:
        return self._cancelled

    def set_cancel_callback(self, callback):
        """设置取消下载时的回调（用于通知 service 停止下载）。"""
        self._cancel_callback = callback

    def set_downloading(self):
        """下载开始后隐藏取消按钮的禁用状态。"""
        self._cancel_btn.setEnabled(True)

    def closeEvent(self, event):
        """关闭对话框时标记为取消并通知 service。"""
        if not self._cancelled:
            self._cancelled = True
            if self._cancel_callback:
                self._cancel_callback()
        super().closeEvent(event)

    @QtCore.Slot(int, int)
    def update_progress(self, downloaded: int, total: int):
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
    def set_status(self, text: str):
        self._status_label.setText(text)
