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

from src.app.runtime import wait_for_managed_threads
from src.services.factory import ServiceFactory
from src.ui.components import StatsCard, TodayStatusCard
from src.ui.components.dialog_buttons import make_dialog_button
from src.ui.controllers.dialog_controller import DialogCoordinator
from src.ui.controllers.poll_controller import PollController
from src.ui.controllers.tray_controller import TrayController
from src.ui.controllers.update_controller import UpdateFlowController
from src.ui.models import build_dashboard_view_state
from src.ui.theme.metrics import CONTROL_SPACING, PAGE_MARGIN, SECTION_SPACING
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
        self.today_card.edit_start_requested.connect(self.dialogs.on_edit_start)
        self.today_card.manual_off_requested.connect(self.dialogs.on_manual_off)

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
        layout.setSpacing(SECTION_SPACING)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)

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
        self.today_card = TodayStatusCard()
        # 保留旧属性，兼容现有测试和后续外部调用。
        self.edit_start_btn = self.today_card.edit_start_button
        self.off_btn = self.today_card.manual_off_button
        self.start_label = self.today_card.start_label
        self.worked_label = self.today_card.worked_label
        self.eta_label = self.today_card.eta_label
        self.progress_card = self.today_card.progress_card
        self.progress_label = self.progress_card.progress_label
        self.progress_bar = self.progress_card.progress_bar
        layout.addWidget(self.today_card)

        # ── 周/月统计卡片 ──
        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(CONTROL_SPACING + 4)
        self.week_card = StatsCard("本期概览")
        self.month_card = StatsCard("本月概览")
        cards.addWidget(self.week_card)
        cards.addWidget(self.month_card)
        layout.addLayout(cards)

        layout.addStretch()

        # ── 底部功能按钮 ──
        btn_box = QtWidgets.QHBoxLayout()
        btn_box.setSpacing(CONTROL_SPACING)
        for label, handler in [
            ("设置", self.dialogs.on_settings),
            ("日历", self.dialogs.on_history),
            ("请假", self.dialogs.on_leave),
            ("导出", self.dialogs.on_export),
        ]:
            btn = make_dialog_button(label, "secondary", handler)
            btn_box.addWidget(btn)
        layout.addLayout(btn_box)

    # ─── UI 刷新 ──────────────────────────────────────────

    def refresh_ui(self) -> None:
        """刷新主界面所有实时数据：今日状态 + 周/月统计卡片 + 托盘图标。"""
        # ── 日期（跨天后自动更新）──
        today = compute_work_date(datetime.now())
        weekday_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        self.date_label.setText(f"{today.year}年{today.month}月{today.day}日 {weekday_name}")

        stats = self.factory.stats_service
        status = stats.get_today_status()

        view_state = build_dashboard_view_state(status, datetime.now())
        self.start_label.setText(view_state.start_text)
        self.progress_card.set_progress(view_state.worked_hours, view_state.required_hours)
        self.worked_label.setText(f"{view_state.worked_hours:.1f}h")
        self.eta_label.setText(view_state.eta_text)

        # ── 托盘图标 ──
        self.tray.update_icon(status)

        # ── 本期卡片 ──
        period = stats.get_period_stats()
        self.week_card.update_stats(period)

        # ── 本月卡片 ──
        month = stats.get_month_stats()
        self.month_card.update_stats(month)

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
        wait_for_managed_threads(timeout=5.0)
        QtWidgets.QApplication.quit()
