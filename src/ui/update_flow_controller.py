"""
update_flow_controller - 更新流程控制器
========================================

管理更新检查/下载/安装流程。
从 MainWindowUI 拆分而来，只管更新相关流程。

通过 DialogCoordinator 打开更新确认窗（非模态），
通过 update_check_finished 信号跨线程回主线程。

版本: 0.16.0
"""

from __future__ import annotations

import logging

from PySide6 import QtCore, QtWidgets

from src.services.factory import ServiceFactory
from src.services.update_service import UpdateService
from src.ui.dialog_coordinator import DialogCoordinator
from src.ui.update_dialog import UpdateConfirmDialogUI, UpdateProgressDialogUI
from src.utils.managed_threads import start_managed_thread

logger = logging.getLogger(__name__)


class UpdateFlowController(QtCore.QObject):
    """更新检查/下载/安装流程控制器。

    Args:
        parent:   父窗口（MainWindowUI）
        factory:  ServiceFactory 实例
        dialogs:  DialogCoordinator 实例（用于打开确认窗 + 消息提示）
    """

    # 内部信号（子线程 → 主线程）
    update_check_finished = QtCore.Signal(object)

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        factory: ServiceFactory,
        dialogs: DialogCoordinator,
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self._factory = factory
        self._update_service: UpdateService = factory.update_service
        self._dialogs = dialogs
        self._update_checking = False

        self.update_check_finished.connect(self._on_update_check_finished)

    def on_check_update(self) -> None:
        """托盘菜单「检查更新」手动触发。子线程执行网络请求，不阻塞 UI。"""
        if self._update_checking:
            return
        self._update_checking = True

        def worker() -> None:
            try:
                info = self._update_service.check_for_updates()
                self._update_service.mark_checked()
                self.update_check_finished.emit(("manual", info))
            except Exception as e:
                logger.warning("[Update] 检查失败：%s", e)
                self.update_check_finished.emit(("manual", "error"))

        start_managed_thread(worker, name="manual-update-check")

    def check_update_after_confirm(self) -> None:
        """次日确认完成后自动检查更新（每天一次），子线程执行不阻塞 UI。

        自动检查路径不弹"已是最新"/"检查失败"提示——静默处理。
        用 update_check_finished 信号但区分手动/自动：自动路径用 "auto" 标记。
        """
        if self._update_checking:
            return
        self._update_checking = True
        record = self._factory.record_service
        record.mark_yesterday_checked()

        def worker() -> None:
            try:
                info = self._update_service.check_for_updates()
                self._update_service.mark_checked()
                self.update_check_finished.emit(("auto", info))
            except Exception as e:
                logger.warning("[Update] 自动检查失败：%s", e)
                self.update_check_finished.emit(("auto", "error"))

        start_managed_thread(worker, name="auto-update-check")

    @QtCore.Slot(object)
    def _on_update_check_finished(self, payload: tuple) -> None:
        """更新检查完成，在主线程处理结果。

        payload 格式：(来源标记, 结果)
            ("manual", UpdateInfo) → 有新版，弹确认窗
            ("manual", None)       → 已是最新
            ("manual", "error")    → 检查失败
            ("auto", UpdateInfo)   → 有新版，弹确认窗
            ("auto", None)         → 无新版，静默
        """
        source, info = payload

        self._update_checking = False

        if source == "auto":
            if info and info != "error":
                self._show_update_confirm(info)
            return

        # 手动检查路径
        if info == "error":
            self._dialogs.msg_warning("检查更新", "检查失败，请稍后重试")
        elif info:
            self._show_update_confirm(info)
        else:
            self._dialogs.msg_information("检查更新", "已是最新版本")

    def _show_update_confirm(self, info: object) -> None:
        """弹出更新确认窗（非模态），确认后下载安装。"""
        dlg = UpdateConfirmDialogUI(info, self._parent)

        def on_finished(result_code: int) -> None:
            if result_code == QtWidgets.QDialog.Accepted:
                self._download_and_install(info)

        self._dialogs.open(dlg, on_finished)

    def _download_and_install(self, info: object) -> None:
        """下载并安装更新。"""
        progress = UpdateProgressDialogUI(self._parent)
        progress.show()
        self._update_service.reset_cancel()
        progress.set_cancel_callback(self._update_service.cancel_download)

        def on_finished(_: int) -> None:
            pass  # DialogCoordinator 已管理 _busy，此处无需额外处理

        progress.finished.connect(on_finished)

        def on_progress(downloaded: int, total: int) -> None:
            # 通过 QMetaObject 在主线程更新 UI，避免跨线程操作 Qt 控件崩溃
            QtCore.QMetaObject.invokeMethod(
                progress,
                "update_progress",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(int, downloaded),
                QtCore.Q_ARG(int, total),
            )

        def worker() -> None:
            dmg_path = self._update_service.download_update(info.dmg_url, on_progress)
            # 检查是否被用户取消
            if progress.is_cancelled():
                QtCore.QMetaObject.invokeMethod(
                    progress,
                    "set_status",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, "已取消下载"),
                )
                QtCore.QMetaObject.invokeMethod(progress, "close", QtCore.Qt.QueuedConnection)
                return
            if not dmg_path or not self._update_service.verify_update(dmg_path, info.length):
                QtCore.QMetaObject.invokeMethod(
                    progress,
                    "set_status",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, "下载失败，请稍后重试"),
                )
                return
            QtCore.QMetaObject.invokeMethod(
                progress,
                "set_status",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, "下载完成，正在安装并重启..."),
            )
            ok = self._update_service.install_and_restart(dmg_path)
            if not ok:
                QtCore.QMetaObject.invokeMethod(
                    progress,
                    "set_status",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, "无法自动安装（开发环境）"),
                )
                return
            # 安装脚本已启动，退出主进程让脚本替换 .app 并重启
            QtCore.QMetaObject.invokeMethod(
                QtWidgets.QApplication.instance(), "quit", QtCore.Qt.QueuedConnection
            )

        start_managed_thread(worker, name="update-download")
