"""
pmset_summary_dialog - pmset 近 7 天推断弹窗
=============================================

从 `pmset -g log` 日志读取近 7 天的 UserIsActive 事件，
推断每天的上下班时间，展示并与 DB 已有记录对比，
用户可选择性地把推断结果写入 DB。

功能说明：
    本功能仅能推断用户使用电脑的情况，无法区分公司/家里。
    如有在家使用电脑，请手动更改下班时间。

版本: 0.17.2
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from functools import partial

from PySide6 import QtCore, QtGui, QtWidgets

from src.app.runtime import start_managed_thread
from src.data.models import PmsetDailySummary
from src.services.factory import ServiceFactory
from src.services.tracking_service import TrackingService
from src.ui.dialog_buttons import make_dialog_button
from src.utils.date_utils import WEEKDAY_NAMES

logger = logging.getLogger(__name__)


class PmsetSummaryDialogUI(QtWidgets.QDialog):
    """pmset 近 7 天上班情况推断弹窗。

    展示近 7 天每天的 pmset 推断上下班时间和已有记录状态，
    提供「应用上班」「应用下班」按钮，遵循保护策略不覆盖已有手动/请假记录。

    Args:
        parent:  父窗口
        factory: ServiceFactory 实例（必须由调用方传入，UI 层不自行创建）
    """

    # 子线程 → 主线程的数据传递信号（Q_ARG 不支持 Python list，改用 Signal）
    _summaries_loaded = QtCore.Signal(object)
    _db_state_refreshed = QtCore.Signal(object)
    _apply_done = QtCore.Signal(bool, str, str)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        factory: ServiceFactory | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("近 7 天工时回溯")
        self.setMinimumSize(720, 520)
        # 设为模态，确保子弹窗始终在父弹窗前面（用户反馈期望）
        self.setModal(True)
        if factory is None:
            raise ValueError("PmsetSummaryDialogUI 必须传入 factory 实例")
        self._tracking: TrackingService = factory.tracking_service
        self._pending_msg: QtWidgets.QDialog | None = None  # 当前非模态子弹窗引用，防止 GC
        self._closing = False
        self._cancel_event = threading.Event()
        self._worker_lock = threading.Lock()
        self._workers: set[threading.Thread] = set()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        # ── 顶部说明 ──
        hint = QtWidgets.QLabel(
            "本功能仅能推断用户使用电脑的情况，如有在家使用电脑，请手动更改下班时间"
        )
        hint.setObjectName("SmallSec")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 加载状态标签 ──
        self.loading_label = QtWidgets.QLabel("加载中...")
        self.loading_label.setObjectName("SmallSec")
        self.loading_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.loading_label)

        # ── 表格 ──
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["日期", "推断上班", "推断下班", "已有记录", "应用上班", "应用下班"]
        )
        self.table.verticalHeader().setVisible(False)
        # 拉大行距，避免内容挤在一起
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        # 表格字号对齐日历主题（12px），表头稍小（11px）
        self.table.setStyleSheet(
            "QTableWidget { font-size: 12px; }"
            "QHeaderView::section { font-size: 11px; padding: 4px 8px; }"
        )
        header = self.table.horizontalHeader()
        # 所有列设为 Stretch，窗口缩放时按初始比例等比拉伸
        # 初始比例通过 resizeSection 设定，Stretch 模式按当前宽度比例分配额外空间
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        # 设初始列宽：应用上班/下班两列最窄，已有记录列最宽（信息多）
        # 日期 / 推断上班 / 推断下班 三列中等
        header.resizeSection(0, 130)  # 日期
        header.resizeSection(1, 90)  # 推断上班
        header.resizeSection(2, 90)  # 推断下班
        header.resizeSection(3, 200)  # 已有记录
        header.resizeSection(4, 76)  # 应用上班（最窄）
        header.resizeSection(5, 76)  # 应用下班（最窄）
        layout.addWidget(self.table)

        # ── 底部按钮 ──
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = make_dialog_button("刷新", "secondary", self._on_refresh)
        btn_row.addWidget(refresh_btn)
        close_btn = make_dialog_button("关闭", "primary", self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # 初始数据
        self._summaries: list[PmsetDailySummary] = []
        self._loading = False

        # 子线程 → 主线程的信号连接
        self._summaries_loaded.connect(self._on_loaded)
        self._db_state_refreshed.connect(self._on_db_state_refreshed)
        self._apply_done.connect(self._on_apply_done)

        # 首次加载
        self._load_async()

    # ─── 数据加载 ──────────────────────────────────────────

    def _load_async(self) -> None:
        """子线程读取 pmset 推断 + DB 状态，避免阻塞 UI。"""
        if self._loading or self._closing:
            return
        self._loading = True
        self.loading_label.setText("加载中...")
        self.loading_label.setVisible(True)
        self.table.setRowCount(0)

        def worker() -> None:
            try:
                summaries = self._tracking.get_recent_pmset_summary(
                    days=7, cancel_event=self._cancel_event
                )
            except Exception as e:
                logger.exception("pmset 推断读取失败：%s", e)
                summaries = []
            if self._cancel_event.is_set() or self._closing:
                return
            try:
                self._summaries_loaded.emit(summaries)
            except RuntimeError:
                # dialog 已被销毁（测试或快速关闭场景），忽略
                pass

        self._start_worker(worker)

    def _start_worker(self, target: Callable[[], None]) -> None:
        """启动并登记线程，避免窗口关闭后留下不可控的后台任务。"""

        def run() -> None:
            target()

        thread = start_managed_thread(run, name="pmset-summary")
        with self._worker_lock:
            self._workers.add(thread)

    def _on_loaded(self, summaries: object) -> None:
        """子线程读取完成后在主线程渲染表格。"""
        if self._closing:
            return
        self._loading = False
        if isinstance(summaries, list):
            self._summaries = [s for s in summaries if isinstance(s, PmsetDailySummary)]
        else:
            self._summaries = []
        self.loading_label.setVisible(False)
        self._render_table()

    def _render_table(self) -> None:
        """渲染表格内容。"""
        self.table.setRowCount(len(self._summaries))
        for row, s in enumerate(self._summaries):
            # 日期
            weekday = WEEKDAY_NAMES[s.work_date.weekday()]
            date_text = f"{s.work_date.isoformat()} {weekday}"
            date_item = QtWidgets.QTableWidgetItem(date_text)
            date_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, 0, date_item)

            # 推断上班
            first_text = s.first_active.strftime("%H:%M") if s.first_active else "--"
            first_item = QtWidgets.QTableWidgetItem(first_text)
            first_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, 1, first_item)

            # 推断下班
            last_text = s.last_active.strftime("%H:%M") if s.last_active else "--"
            last_item = QtWidgets.QTableWidgetItem(last_text)
            last_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, 2, last_item)

            # 已有记录状态
            existing_text = self._format_existing_status(s)
            existing_item = QtWidgets.QTableWidgetItem(existing_text)
            existing_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, 3, existing_item)

            # 应用上班按钮（在单元格内居中：用容器 + 两侧 stretch）
            apply_start_btn = make_dialog_button(
                "应用上班",
                "secondary",
                partial(self._on_apply_start, row),
                fixed_size=(76, 26),
            )
            # 表格内按钮字号对齐表格内容（12px），比主题默认 13px 小一号
            apply_start_btn.setStyleSheet("QPushButton { font-size: 12px; padding: 2px 6px; }")
            self._configure_apply_button(apply_start_btn, s, is_start=True)
            self.table.setCellWidget(row, 4, self._wrap_centered(apply_start_btn))

            # 应用下班按钮
            apply_end_btn = make_dialog_button(
                "应用下班",
                "secondary",
                partial(self._on_apply_end, row),
                fixed_size=(76, 26),
            )
            apply_end_btn.setStyleSheet("QPushButton { font-size: 12px; padding: 2px 6px; }")
            self._configure_apply_button(apply_end_btn, s, is_start=False)
            self.table.setCellWidget(row, 5, self._wrap_centered(apply_end_btn))

    @staticmethod
    def _wrap_centered(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """将控件包裹在居中的容器中（用于 QTableWidget 单元格内居中按钮）。

        QTableWidget.setCellWidget 默认把 widget 填满整个单元格，
        按钮会靠左上对齐。用容器 + QHBoxLayout 两侧 stretch 实现居中。

        Args:
            widget: 待居中的控件

        Returns:
            包裹后的容器 widget
        """
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch()
        layout.addWidget(widget)
        layout.addStretch()
        return container

    def _format_existing_status(self, s: PmsetDailySummary) -> str:
        """格式化已有记录状态描述。"""
        if s.leave_type:
            from src.config import LEAVE_TYPES

            return f"请假-{LEAVE_TYPES.get(s.leave_type, s.leave_type)}"
        if s.has_start_record and s.has_end_record:
            src = f"（{s.source}）" if s.source else ""
            return f"已记录{src}"
        if s.has_start_record:
            src = f"（{s.source}）" if s.source else ""
            return f"仅上班{src}"
        return "无记录"

    def _configure_apply_button(
        self,
        btn: QtWidgets.QPushButton,
        s: PmsetDailySummary,
        *,
        is_start: bool,
    ) -> None:
        """根据当前记录状态配置按钮的启用/禁用与 tooltip。

        Args:
            btn:      待配置的按钮
            s:        当前行的 PmsetDailySummary
            is_start: True=应用上班, False=应用下班
        """
        # 有请假记录 → 禁用
        if s.leave_type:
            btn.setEnabled(False)
            btn.setToolTip("已请假，无法应用")
            return
        # 已有手动记录 → 禁用
        if s.source == "manual":
            btn.setEnabled(False)
            btn.setToolTip("已有手动记录，不覆盖")
            return
        # 应用上班：无推断 / 已有上班记录 → 禁用
        if is_start:
            if s.first_active is None:
                btn.setEnabled(False)
                btn.setToolTip("未检测到 pmset 活动")
                return
            if s.has_start_record:
                btn.setEnabled(False)
                btn.setToolTip("已有上班记录，不覆盖")
                return
        # 应用下班：无推断 / 无上班记录 / 已有下班记录 → 禁用
        else:
            if s.last_active is None:
                btn.setEnabled(False)
                btn.setToolTip("未检测到 pmset 活动")
                return
            if not s.has_start_record:
                btn.setEnabled(False)
                btn.setToolTip("无上班记录，无法应用下班")
                return
            if s.has_end_record:
                btn.setEnabled(False)
                btn.setToolTip("已有下班记录，不覆盖")
                return
        btn.setToolTip("")

    # ─── 事件处理 ──────────────────────────────────────────

    def _on_refresh(self) -> None:
        """刷新按钮：重新读 pmset 推断 + DB 状态。"""
        if self._closing:
            return
        self._cancel_event.clear()
        self._load_async()

    def _on_apply_start(self, row: int) -> None:
        """应用上班按钮：把 pmset 推断上班时间写入 DB。"""
        if row >= len(self._summaries):
            return
        s = self._summaries[row]
        first_active = s.first_active
        if first_active is None:
            return
        work_date = s.work_date

        def worker() -> None:
            if self._cancel_event.is_set():
                return
            applied = self._tracking.apply_pmset_start_time(work_date, first_active)
            if self._cancel_event.is_set() or self._closing:
                return
            try:
                self._apply_done.emit(applied, "上班", work_date.isoformat())
            except RuntimeError:
                pass

        self._start_worker(worker)

    def _on_apply_end(self, row: int) -> None:
        """应用下班按钮：把 pmset 推断下班时间写入 DB。"""
        if row >= len(self._summaries):
            return
        s = self._summaries[row]
        last_active = s.last_active
        if last_active is None:
            return
        work_date = s.work_date

        def worker() -> None:
            if self._cancel_event.is_set():
                return
            applied = self._tracking.apply_pmset_end_time(work_date, last_active)
            if self._cancel_event.is_set() or self._closing:
                return
            try:
                self._apply_done.emit(applied, "下班", work_date.isoformat())
            except RuntimeError:
                pass

        self._start_worker(worker)

    def _on_apply_done(self, applied: bool, kind: str, work_date_str: str) -> None:
        """应用完成后刷新表格（不重新读 pmset，只查 DB）。"""
        if applied:
            self._show_msg("已应用", f"{work_date_str} {kind}时间已应用")
        else:
            self._show_msg("跳过", f"{work_date_str} {kind}时间因保护策略未应用")

        # 局部刷新该行的 DB 状态（重新查 DB，不重读 pmset）
        self._refresh_db_state()

    def _refresh_db_state(self) -> None:
        """应用后局部刷新 DB 状态（不重新读 pmset）。"""
        if not self._summaries:
            return

        def worker() -> None:
            if self._cancel_event.is_set() or self._closing:
                return
            # 重新查 DB 更新 has_start_record / has_end_record / source / leave_type
            updated: list[PmsetDailySummary] = []
            for s in self._summaries:
                daily = self._tracking._worktime_repo.get(s.work_date)
                new_s = PmsetDailySummary(
                    work_date=s.work_date,
                    first_active=s.first_active,
                    last_active=s.last_active,
                    has_start_record=bool(daily and daily.get("start_time")),
                    has_end_record=bool(daily and daily.get("end_time")),
                    source=daily.get("source") if daily else None,
                    leave_type=daily.get("leave_type") if daily else None,
                )
                updated.append(new_s)
            if self._cancel_event.is_set() or self._closing:
                return
            try:
                self._db_state_refreshed.emit(updated)
            except RuntimeError:
                pass

        self._start_worker(worker)

    def _on_db_state_refreshed(self, updated: object) -> None:
        """DB 状态刷新完成后重渲染表格。"""
        if self._closing:
            return
        if isinstance(updated, list):
            self._summaries = [s for s in updated if isinstance(s, PmsetDailySummary)]
        else:
            self._summaries = []
        self._render_table()

    # ─── 消息提示 ──────────────────────────────────────────

    def _show_msg(self, title: str, text: str) -> None:
        """自定义消息提示框（模态，确保在父弹窗前面）。

        沿用 make_dialog_button 避免 QMessageBox 焦点链问题，
        用 exec() 模态显示确保消息框阻塞父弹窗交互。
        """
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(320)
        # 消息框也设为模态，确保在父弹窗前面
        dlg.setModal(True)
        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(24, 20, 24, 16)
        v.setSpacing(12)
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        v.addWidget(label)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        ok_btn = make_dialog_button("确定", "primary", dlg.accept)
        btn_row.addWidget(ok_btn)
        v.addLayout(btn_row)
        self._pending_msg = dlg

        def on_finished(_: int) -> None:
            self._pending_msg = None

        dlg.finished.connect(on_finished)
        dlg.exec()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """关闭前取消并等待本窗口启动的后台任务结束。"""
        self._closing = True
        self._cancel_event.set()
        with self._worker_lock:
            workers = list(self._workers)
        for worker in workers:
            worker.join(timeout=2)
        with self._worker_lock:
            self._workers.clear()
        super().closeEvent(event)
