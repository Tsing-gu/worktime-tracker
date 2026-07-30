"""
main_window - 主窗口
======================

工时计算器的主界面。MainWindowUI 只负责 UI 构建与 refresh_ui，
业务逻辑委托给 4 个 controller:
    - PollController:        定时器 + 轮询 + 信号分发
    - TrayController:        托盘图标 + 右键菜单 + 时长卡
    - DialogCoordinator:     弹窗管理 + 消息提示
    - UpdateFlowController:  更新检查/下载/安装流程

版本: 0.16.0
"""

from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets

from src.services.factory import ServiceFactory
from src.ui.dialog_buttons import make_dialog_button
from src.ui.dialog_coordinator import DialogCoordinator
from src.ui.poll_controller import PollController
from src.ui.tray_controller import TrayController
from src.ui.update_flow_controller import UpdateFlowController
from src.utils.date_utils import compute_work_date
from src.utils.paths import resource_path


class MainWindowUI(QtWidgets.QMainWindow):
    """工时计算器主窗口。

    只负责 UI 构建与 refresh_ui，业务逻辑通过 4 个 controller 处理。

    Attributes:
        factory:  ServiceFactory 实例，持有所有子服务
        dialogs:  DialogCoordinator 实例（弹窗管理）
        tray:     TrayController 实例（托盘交互）
        poll:     PollController 实例（定时轮询）
        update_flow: UpdateFlowController 实例（更新流程）
    """

    def __init__(self) -> None:
        """初始化主窗口：创建 service、controller、UI、连接信号。"""
        super().__init__()
        self.setWindowTitle("工时计算器")
        self.setMinimumSize(640, 600)
        self.resize(680, 640)

        # 服务工厂（持有所有子服务）
        self.factory = ServiceFactory()

        # 弹窗协调器（先创建，_init_ui 按钮要连接到它的方法）
        self.dialogs = DialogCoordinator(self, self.factory)

        # UI 构建（按钮连接到 self.dialogs.on_*）
        self._init_ui()

        # 托盘控制器（创建后自动初始化托盘图标）
        self.tray = TrayController(self, self.factory.stats_service)

        # 轮询控制器（含定时器 + 启动初始化）
        self.poll = PollController(self, self.factory, is_busy=lambda: self.dialogs.busy)

        # 更新流程控制器
        self.update_flow = UpdateFlowController(self, self.factory, self.dialogs)

        # 连接跨 controller 信号
        self._connect_signals()

        # 主题变更 → 刷新 UI
        from src.ui.theme import ThemeManagerUI

        ThemeManagerUI.instance().theme_changed.connect(self.refresh_ui)

    def _connect_signals(self) -> None:
        """连接跨 controller 信号，controller 之间不直接引用。"""
        # PollController → MainWindowUI / DialogCoordinator
        self.poll.holiday_loaded.connect(self.poll.on_holiday_loaded)
        self.poll.refresh_requested.connect(self.refresh_ui)
        self.poll.resume_requested.connect(self.dialogs.confirm_resume)
        self.poll.check_yesterday_requested.connect(self.dialogs.check_yesterday_confirm)

        # DialogCoordinator → MainWindowUI / UpdateFlowController
        self.dialogs.refresh_requested.connect(self.refresh_ui)
        self.dialogs.update_check_requested.connect(self.update_flow.check_update_after_confirm)
        self.dialogs.manual_check_update_requested.connect(self.update_flow.on_check_update)

        # TrayController → MainWindowUI / DialogCoordinator / UpdateFlowController
        self.tray.show_main_requested.connect(self.show_normal)
        self.tray.manual_off_requested.connect(self.dialogs.on_manual_off)
        self.tray.check_update_requested.connect(self.update_flow.on_check_update)
        self.tray.quit_requested.connect(self.quit_app)

    # ─── UI 初始化 ─────────────────────────────────────────

    def _init_ui(self) -> None:
        """构建主界面所有可见元素。"""
        self.setWindowIcon(QtGui.QIcon(resource_path("resources/app.icns")))
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(28, 28, 28, 24)

        # ── 日期标题 ──
        today = compute_work_date(datetime.now())
        weekday_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        self.date_label = QtWidgets.QLabel(
            f"{today.year}年{today.month}月{today.day}日 {weekday_name}"
        )
        self.date_label.setObjectName("DateLabel")
        self.date_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.date_label)

        # ── 今日状态卡片 ──
        status_card = QtWidgets.QFrame()
        status_card.setObjectName("Card")
        status_layout = QtWidgets.QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(14)

        # 按钮行：修改上班（左）| 手动下班（右）
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(12)

        self.edit_start_btn = make_dialog_button(
            "修改上班", "secondary", self.dialogs.on_edit_start
        )
        btn_row.addWidget(self.edit_start_btn)
        btn_row.addStretch()

        self.off_btn = make_dialog_button("手动下班", "primary", self.dialogs.on_manual_off)
        btn_row.addWidget(self.off_btn)
        status_layout.addLayout(btn_row)

        # 信息行：上班时间 | 已工作 | 预计下班
        info_top = QtWidgets.QHBoxLayout()
        info_top.setSpacing(24)

        start_vbox = QtWidgets.QVBoxLayout()
        start_vbox.setSpacing(2)
        self.start_label = QtWidgets.QLabel("--:--")
        self.start_label.setObjectName("WorkedValue")
        self.start_label.setAlignment(QtCore.Qt.AlignCenter)
        start_vbox.addWidget(self.start_label)
        start_sub = QtWidgets.QLabel("上班时间")
        start_sub.setObjectName("WorkedSub")
        start_sub.setAlignment(QtCore.Qt.AlignCenter)
        start_vbox.addWidget(start_sub)
        info_top.addLayout(start_vbox)

        info_top.addStretch()

        worked_vbox = QtWidgets.QVBoxLayout()
        worked_vbox.setSpacing(2)
        self.worked_label = QtWidgets.QLabel("0.0h")
        self.worked_label.setObjectName("WorkedValue")
        self.worked_label.setAlignment(QtCore.Qt.AlignCenter)
        worked_vbox.addWidget(self.worked_label)
        self.worked_sub = QtWidgets.QLabel("当前已工作")
        self.worked_sub.setObjectName("WorkedSub")
        self.worked_sub.setAlignment(QtCore.Qt.AlignCenter)
        worked_vbox.addWidget(self.worked_sub)
        info_top.addLayout(worked_vbox)

        info_top.addStretch()

        eta_vbox = QtWidgets.QVBoxLayout()
        eta_vbox.setSpacing(2)
        self.eta_label = QtWidgets.QLabel("--:--")
        self.eta_label.setObjectName("WorkedValue")
        self.eta_label.setAlignment(QtCore.Qt.AlignCenter)
        eta_vbox.addWidget(self.eta_label)
        eta_sub = QtWidgets.QLabel("预计下班")
        eta_sub.setObjectName("WorkedSub")
        eta_sub.setAlignment(QtCore.Qt.AlignCenter)
        eta_vbox.addWidget(eta_sub)
        info_top.addLayout(eta_vbox)

        status_layout.addLayout(info_top)

        # 今日进度条 + 达成度
        progress_area = QtWidgets.QVBoxLayout()
        progress_area.setSpacing(6)
        self.progress_label = QtWidgets.QLabel("今日目标 8.0h  0%")
        self.progress_label.setObjectName("SmallSec")
        self.progress_label.setAlignment(QtCore.Qt.AlignCenter)
        progress_area.addWidget(self.progress_label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setTextVisible(False)
        progress_area.addWidget(self.progress_bar)
        status_layout.addLayout(progress_area)

        layout.addWidget(status_card)

        # ── 周/月统计卡片 ──
        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(12)
        self.week_card = self._make_card("本期概览")
        self.month_card = self._make_card("本月概览")
        cards.addWidget(self.week_card)
        cards.addWidget(self.month_card)
        layout.addLayout(cards)

        layout.addStretch()

        # ── 底部功能按钮 ──
        btn_box = QtWidgets.QHBoxLayout()
        btn_box.setSpacing(10)
        for label, handler in [
            ("设置", self.dialogs.on_settings),
            ("日历", self.dialogs.on_history),
            ("请假", self.dialogs.on_leave),
            ("导出", self.dialogs.on_export),
        ]:
            btn = make_dialog_button(label, "secondary", handler)
            btn_box.addWidget(btn)
        layout.addLayout(btn_box)

    def _make_card(self, title: str) -> QtWidgets.QFrame:
        """创建一个统计卡片（周/月概览）。

        Args:
            title: 卡片标题（"本期概览" / "本月概览"）

        Returns:
            QFrame 卡片对象
        """
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        v = QtWidgets.QVBoxLayout(card)
        v.setSpacing(6)
        v.setContentsMargins(16, 16, 16, 16)

        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setObjectName("CardTitle")
        v.addWidget(title_lbl)

        divider = QtWidgets.QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)
        v.addWidget(divider)
        v.addSpacing(2)

        self._card_labels: dict[str, QtWidgets.QWidget] = getattr(self, "_card_labels", {})
        for key in ["line1", "line2", "line3"]:
            lbl = QtWidgets.QLabel("")
            lbl.setObjectName("CardLine")
            v.addWidget(lbl)
            self._card_labels[f"{title}_{key}"] = lbl

        v.addSpacing(4)
        bar = QtWidgets.QProgressBar()
        bar.setObjectName("CardBar")
        bar.setTextVisible(False)
        v.addWidget(bar)
        self._card_labels[f"{title}_bar"] = bar
        return card

    # ─── UI 刷新 ──────────────────────────────────────────

    def refresh_ui(self) -> None:
        """刷新主界面所有实时数据：今日状态 + 周/月统计卡片 + 托盘图标。"""
        # ── 日期（跨天后自动更新）──
        today = compute_work_date(datetime.now())
        weekday_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        self.date_label.setText(f"{today.year}年{today.month}月{today.day}日 {weekday_name}")

        stats = self.factory.stats_service
        status = stats.get_today_status()

        # ── 上班时间 ──
        if status.start_time:
            self.start_label.setText(status.start_time.strftime("%H:%M"))
        else:
            self.start_label.setText("--:--")

        # ── 今日进度 ──
        required = status.required_hours
        self._style_progress_bar(self.progress_bar, status.worked_hours, required)
        pct = int(status.worked_hours / required * 100) if required > 0 else 0
        self.progress_label.setText(f"今日目标 {required:.1f}h  {pct}%")

        self.worked_label.setText(f"{status.worked_hours:.1f}h")

        # ── 预计下班时间 ──
        from datetime import timedelta as _td

        if status.start_time and not status.end_time:
            remaining = max(0, required - status.worked_hours)
            eta = datetime.now() + _td(hours=remaining)
            self.eta_label.setText(eta.strftime("%H:%M"))
        elif status.end_time:
            self.eta_label.setText("已下班")
        else:
            self.eta_label.setText("--:--")

        # ── 托盘图标 ──
        self.tray.update_icon(status)

        # ── 本期卡片 ──
        period = stats.get_period_stats()
        if period.is_rest:
            self._card_labels["本期概览_line1"].setText("休息中")
            self._card_labels["本期概览_line2"].setText("")
            self._card_labels["本期概览_line3"].setText("")
            bar = self._card_labels["本期概览_bar"]
            bar.setStyleSheet("")
            bar.setMaximum(100)
            bar.setValue(0)
        else:
            self._card_labels["本期概览_line1"].setText(
                f"已工作 {period.worked_days}天 / {period.total_workdays}天"
            )
            self._card_labels["本期概览_line2"].setText(
                f"累计 {period.worked_hours:.1f}h / 目标 {period.target_hours:.0f}h"
            )
            if period.remaining_days > 1:
                self._card_labels["本期概览_line3"].setText(
                    f"日均 {period.daily_avg:.1f}h, 剩余{period.remaining_days}天 "
                    f"每天需{period.remaining_per_day:.1f}h达标"
                )
            else:
                left = max(0, period.target_hours - period.worked_hours)
                self._card_labels["本期概览_line3"].setText(f"今天干完就放假啦！还剩{left:.1f}h")
            bar = self._card_labels["本期概览_bar"]
            assert isinstance(bar, QtWidgets.QProgressBar)
            self._style_progress_bar(bar, period.worked_hours, period.target_hours)

        # ── 本月卡片 ──
        month = stats.get_month_stats()
        self._card_labels["本月概览_line1"].setText(
            f"已工作 {month.worked_days}天 / {month.total_workdays}天"
        )
        self._card_labels["本月概览_line2"].setText(
            f"累计 {month.worked_hours:.1f}h / 目标 {month.target_hours:.0f}h"
        )
        if month.remaining_days > 1:
            self._card_labels["本月概览_line3"].setText(
                f"日均 {month.daily_avg:.1f}h, 剩余{month.remaining_days}天 "
                f"每天需{month.remaining_per_day:.1f}h达标"
            )
        else:
            left = max(0, month.target_hours - month.worked_hours)
            self._card_labels["本月概览_line3"].setText(f"今天干完就放假啦！还剩{left:.1f}h")
        bar2 = self._card_labels["本月概览_bar"]
        assert isinstance(bar2, QtWidgets.QProgressBar)
        self._style_progress_bar(bar2, month.worked_hours, month.target_hours)

    def _style_progress_bar(
        self, bar: QtWidgets.QProgressBar, worked: float, required: float
    ) -> None:
        """统一设置进度条：按 worked/required 百分比填充，>=100% 变绿，钳制到满格。"""
        from src.ui.theme import get_theme

        t = get_theme()
        reached = required > 0 and worked >= required
        pct = int(worked / required * 100) if required > 0 else 0
        color = t["green"] if reached else t["primary"]
        radius = "3px" if bar.objectName() == "CardBar" else "4px"
        bar.setMaximum(100)
        bar.setValue(min(100, pct))
        bar.setStyleSheet(
            f"QProgressBar {{ background-color: {t['track']}; border: none; border-radius: {radius}; }}"
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: {radius}; }}"
        )

    # ─── 窗口控制 ──────────────────────────────────────────

    def show_normal(self) -> None:
        """显示并激活主窗口（从隐藏/最小化状态恢复）。"""
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """关闭窗口时不退出程序，转入菜单栏托盘继续运行。"""
        event.ignore()
        self.hide()

    def quit_app(self) -> None:
        """退出程序：停止定时器 + 隐藏托盘 + 退出应用。"""
        self.poll.stop()
        self.tray.hide()
        QtWidgets.QApplication.quit()
