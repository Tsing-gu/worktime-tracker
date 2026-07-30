"""
dialog_coordinator - 弹窗协调器
================================

统一管理 MainWindowUI 所有非模态弹窗的 _busy/_pending 状态，
消除 8 行重复的 _busy = True / _pending_dialog = dlg / finished.connect 模板。

核心 API:
    - open(dialog, on_finished) -> bool: 统一打开非模态弹窗
    - busy: 当前是否有弹窗打开
    - msg_information / msg_warning / msg_question: 消息提示框

跨 controller 通信通过信号:
    - refresh_requested: 请求主窗口刷新 UI
    - update_check_requested: 请求 UpdateFlowController 自动检查更新
    - export_finished: 导出完成（跨线程回主线程）

版本: 0.16.0
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta

from PySide6 import QtCore, QtWidgets

from src.services.factory import ServiceFactory
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.services.stats_service import StatsService
from src.services.tracking_service import TrackingService
from src.ui.calendar_dialog import CalendarHistoryDialogUI
from src.ui.confirm_dialog import ConfirmYesterdayDialogUI
from src.ui.dialog_buttons import make_dialog_button
from src.ui.edit_start_dialog import EditStartDialogUI
from src.ui.leave_dialog import LeaveDialogUI
from src.ui.settings_dialog import SettingsDialogUI
from src.utils.date_utils import compute_work_date


class DialogCoordinator(QtCore.QObject):
    """统一管理非模态弹窗的 _busy/_pending 状态与消息提示框。

    所有非模态弹窗通过 open() 打开，自动管理 _busy 与 _pending_dialog，
    避免重复模板代码。消息提示框通过 msg_* 方法调用。

    Args:
        parent:  父窗口（MainWindowUI）
        factory: ServiceFactory 实例
    """

    # 跨 controller 通信信号
    refresh_requested = QtCore.Signal()
    update_check_requested = QtCore.Signal()  # 自动检查（次日确认后）
    manual_check_update_requested = QtCore.Signal()  # 手动检查（设置弹窗触发）
    export_finished = QtCore.Signal(str, bool)

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        factory: ServiceFactory,
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self._factory = factory
        self._tracking: TrackingService = factory.tracking_service
        self._stats: StatsService = factory.stats_service
        self._record: RecordService = factory.record_service
        self._settings: SettingsService = factory.settings_service

        self._busy = False
        self._pending: QtWidgets.QDialog | None = None

        self.export_finished.connect(self._on_export_finished)

    @property
    def busy(self) -> bool:
        """当前是否有未关闭的非模态弹窗。"""
        return self._busy

    def open(
        self,
        dialog: QtWidgets.QDialog,
        on_finished: Callable[[int], None],
    ) -> bool:
        """统一打开非模态弹窗，自动管理 _busy 与 _pending。

        Args:
            dialog:      要打开的 QDialog
            on_finished:  弹窗关闭后的回调，参数为 result_code

        Returns:
            True=已打开，False=因 _busy 被拒绝
        """
        if self._busy:
            return False
        self._busy = True
        self._pending = dialog

        def _on_done(code: int) -> None:
            self._busy = False
            self._pending = None
            on_finished(code)

        dialog.finished.connect(_on_done)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return True

    # ─── 消息提示框 ────────────────────────────────────────

    @staticmethod
    def _msg_box(
        icon: QtWidgets.QMessageBox.Icon,
        parent: QtWidgets.QWidget,
        title: str,
        text: str,
        buttons: QtWidgets.QMessageBox.StandardButton = QtWidgets.QMessageBox.Ok,
    ) -> QtWidgets.QMessageBox:
        """封装 QMessageBox，禁用 autoDefault + StrongFocus，修复按钮需点两次。非模态 show()。"""
        box = QtWidgets.QMessageBox(icon, title, text, buttons, parent)
        for btn in box.buttons():
            btn.setAutoDefault(False)
            btn.setFocusPolicy(QtCore.Qt.StrongFocus)
        box.show()
        box.raise_()
        box.activateWindow()
        return box

    def msg_information(self, title: str, text: str) -> QtWidgets.QMessageBox:
        """信息提示框。"""
        return self._msg_box(
            QtWidgets.QMessageBox.Information,
            self._parent,
            title,
            text,
            QtWidgets.QMessageBox.Ok,
        )

    def msg_warning(self, title: str, text: str) -> QtWidgets.QMessageBox:
        """警告提示框。"""
        return self._msg_box(
            QtWidgets.QMessageBox.Warning,
            self._parent,
            title,
            text,
            QtWidgets.QMessageBox.Ok,
        )

    def msg_question(self, title: str, text: str) -> QtWidgets.QMessageBox:
        """询问提示框（是/否）。"""
        return self._msg_box(
            QtWidgets.QMessageBox.Question,
            self._parent,
            title,
            text,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )

    # ─── 弹窗方法 ──────────────────────────────────────────

    def on_edit_start(self) -> None:
        """修改今日上班时间：非模态弹窗，支持手动输入或从 pmset 读取。"""
        status = self._stats.get_today_status()
        current_start = status.start_time
        current_str = current_start.strftime("%H:%M") if current_start else ""

        dialog = EditStartDialogUI(current_str, self._tracking, self._parent)

        def on_finished(result_code: int) -> None:
            if result_code != QtWidgets.QDialog.Accepted:
                return
            new_str = dialog.get_time_str()
            if not new_str:
                return
            try:
                new_start = self._tracking.edit_start_time(new_str)
                self.refresh_requested.emit()
                self.msg_information("已修改", f"上班时间已更新为 {new_start.strftime('%H:%M')}")
            except ValueError as e:
                self.msg_warning("格式错误", str(e))

        self.open(dialog, on_finished)

    def on_manual_off(self) -> None:
        """手动下班：非模态弹窗确认后通过 tracking.manual_off() 记录。"""
        status = self._stats.get_today_status()
        if not status.has_started:
            self.msg_information("提示", "今天还没有上班记录，无法下班")
            return
        if status.end_time:
            self.msg_information("提示", "今天已经下班了")
            return

        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Question,
            "确认下班",
            f"当前时间：{datetime.now().strftime('%H:%M')}\n"
            f"今日已工作：{status.worked_hours:.1f} 小时"
            f"{'  已达标' if status.is_target_reached else ''}\n\n"
            f"确认以当前时间记录下班？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            self._parent,
        )
        for btn in box.buttons():
            btn.setAutoDefault(False)
            btn.setFocusPolicy(QtCore.Qt.StrongFocus)

        def on_finished(result_code: int) -> None:
            if result_code == QtWidgets.QMessageBox.Yes:
                result = self._tracking.manual_off()
                if result.event == "manual_off" and result.off_time is not None:
                    self.msg_information(
                        "已下班",
                        f"下班时间：{result.off_time.strftime('%H:%M')}\n"
                        f"今日工时：{result.worked_hours:.2f} 小时",
                    )
                    self.refresh_requested.emit()

        # QMessageBox 也是 QDialog 的子类，可用 open 统一管理
        self.open(box, on_finished)

    def on_settings(self) -> None:
        """打开设置弹窗（非模态），确认后保存设置。"""
        dialog = SettingsDialogUI(
            self._settings.get_settings_dict(),
            self._parent,
            on_check_update=self.manual_check_update_requested.emit,
        )

        def on_finished(result_code: int) -> None:
            if result_code == QtWidgets.QDialog.Accepted:
                self._settings.update_from_dict(dialog.get_values())
                self.refresh_requested.emit()

        self.open(dialog, on_finished)

    def on_history(self) -> None:
        """打开日历历史弹窗（非模态）。"""
        dialog = CalendarHistoryDialogUI(self._parent, factory=self._factory)

        def on_finished(_: int) -> None:
            pass

        self.open(dialog, on_finished)

    def on_leave(self) -> None:
        """打开请假弹窗（非模态），确认后通过 record 标记请假。"""
        today = compute_work_date(datetime.now())
        dialog = LeaveDialogUI(self._parent, default_date=today)

        def on_finished(result_code: int) -> None:
            if result_code == QtWidgets.QDialog.Accepted:
                leave_date = dialog.get_date()
                leave_type = dialog.get_leave_type()
                self._record.mark_leave(leave_date, leave_type)
                self.refresh_requested.emit()

        self.open(dialog, on_finished)

    def on_export(self) -> None:
        """导出本月数据为 Excel。"""
        today = compute_work_date(datetime.now())
        if today.month == 12:
            start = date(today.year, 12, 1)
            end = date(today.year, 12, 31)
        else:
            start = date(today.year, today.month, 1)
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)

        dlg = QtWidgets.QDialog(self._parent)
        dlg.setWindowTitle("导出")
        dlg.setMinimumWidth(300)
        dlg_layout = QtWidgets.QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(24, 20, 24, 16)
        dlg_layout.setSpacing(12)

        dlg_layout.addWidget(QtWidgets.QLabel(f"导出本月数据（{start} ~ {end}）"))

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = make_dialog_button("取消", "secondary", dlg.reject, fixed_size=(96, 32))
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        export_btn = make_dialog_button(
            "导出 Excel", "primary", lambda: dlg.done(1), fixed_size=(96, 32)
        )
        btn_row.addWidget(export_btn)
        dlg_layout.addLayout(btn_row)

        def on_finished(result_code: int) -> None:
            if result_code != 1:
                return
            exporter = self._factory.export_service

            def worker() -> None:
                try:
                    path = exporter.to_excel(start, end)
                    self.export_finished.emit(path, True)
                except Exception as e:
                    self.export_finished.emit(str(e), False)

            threading.Thread(target=worker, daemon=True).start()

        self.open(dlg, on_finished)

    @QtCore.Slot(str, bool)
    def _on_export_finished(self, result: str, success: bool) -> None:
        """导出完成后在主线程弹提示。"""
        if success:
            self.msg_information("导出成功", f"文件已保存到：\n{result}")
        else:
            self.msg_warning("导出失败", result)

    # ─── 次日确认 ──────────────────────────────────────────

    def check_yesterday_confirm(self) -> None:
        """检查是否需要弹出次日确认弹窗（非模态）。

        通过 record.check_yesterday() 获取待确认的前一工作日记录，
        弹出 ConfirmYesterdayDialog 供用户确认或修改。
        """
        result = self._record.check_yesterday()
        if result is None:
            return

        prev, daily = result
        required = self._stats.get_required_hours()
        dialog = ConfirmYesterdayDialogUI(prev, daily, required, self._parent)

        def on_finished(result_code: int) -> None:
            if result_code == QtWidgets.QDialog.Accepted:
                end_time = dialog.get_end_time()
                self._record.confirm_yesterday(prev, end_time)
            else:
                self._record.skip_yesterday(prev)
            self._record.mark_yesterday_checked()
            self.refresh_requested.emit()
            # 次日确认完成后触发更新检查（UpdateFlowController 监听）
            self.update_check_requested.emit()

        self.open(dialog, on_finished)

    # ─── 下班后恢复确认 ────────────────────────────────────

    def confirm_resume(self) -> None:
        """下班后检测到用户回来活跃，弹窗确认是否恢复计时（非模态）。

        确认 → 调用 tracking.resume_after_off() 清除下班记录，恢复"工作中"状态
        取消 → 保持下班状态不变
        """
        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Question,
            "恢复计时",
            "检测到您已回来继续工作，是否恢复计时？\n\n"
            "确认 → 清除下班记录，继续追踪工时\n"
            "取消 → 保持当前下班状态",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            self._parent,
        )
        for btn in box.buttons():
            btn.setAutoDefault(False)
            btn.setFocusPolicy(QtCore.Qt.StrongFocus)

        def on_finished(result_code: int) -> None:
            if result_code == QtWidgets.QMessageBox.Yes:
                self._tracking.resume_after_off()
                self.refresh_requested.emit()

        self.open(box, on_finished)
