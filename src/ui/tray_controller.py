"""
tray_controller - 系统托盘控制器
==================================

管理系统托盘图标、右键菜单、左键时长卡弹窗。
从 MainWindowUI 拆分而来，只管托盘相关交互。

托盘菜单动作通过信号通知 MainWindowUI 转发到对应 controller：
    - show_main_requested   → MainWindowUI.show_normal
    - manual_off_requested  → DialogCoordinator.on_manual_off
    - check_update_requested → UpdateFlowController.on_check_update
    - quit_requested        → MainWindowUI.quit_app

版本: 0.16.0
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6 import QtCore, QtGui, QtWidgets

from src.data.models import TodayStatus
from src.services.stats_service import StatsService
from src.ui.theme import get_theme
from src.utils.paths import resource_path


class TrayController(QtCore.QObject):
    """系统托盘图标 + 右键菜单 + 左键时长卡弹窗。

    Args:
        parent:  父窗口（MainWindowUI）
        stats:   StatsService 实例（用于读取今日状态）
    """

    # 托盘菜单动作信号（由 MainWindowUI 连接到对应 handler）
    show_main_requested = QtCore.Signal()
    manual_off_requested = QtCore.Signal()
    check_update_requested = QtCore.Signal()
    quit_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget, stats: StatsService) -> None:
        super().__init__(parent)
        self._parent = parent
        self._stats = stats
        self._tray_popup_menu: QtWidgets.QMenu | None = None
        self._init_tray()

    def _init_tray(self) -> None:
        """初始化菜单栏托盘图标及其右键菜单。"""
        self.tray = QtWidgets.QSystemTrayIcon()
        self.tray.setToolTip("工时计算器")
        icon = QtGui.QIcon(resource_path("resources/app.icns"))
        if icon.isNull():
            icon = self._parent.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setVisible(True)

        # 右键菜单（不使用 setContextMenu，避免左键同时弹出系统菜单）
        self._tray_menu = QtWidgets.QMenu()
        act_show = self._tray_menu.addAction("打开主界面")
        act_show.triggered.connect(self.show_main_requested.emit)
        act_off = self._tray_menu.addAction("手动下班")
        act_off.triggered.connect(self.manual_off_requested.emit)
        act_update = self._tray_menu.addAction("检查更新")
        act_update.triggered.connect(self.check_update_requested.emit)
        self._tray_menu.addSeparator()
        act_quit = self._tray_menu.addAction("退出")
        act_quit.triggered.connect(self.quit_requested.emit)

        # 点击托盘图标（左键弹时长卡，右键弹功能菜单）
        self.tray.activated.connect(self.on_activated)
        self.tray.show()

    def update_icon(self, status: TodayStatus) -> None:
        """更新托盘图标为剩余工时数字。

        未上班/已下班时不更新；上班中显示剩余小时数。

        Args:
            status: TodayStatus 对象
        """
        if not hasattr(self, "tray") or not self.tray.isVisible():
            return

        if not status.has_started or status.end_time:
            return

        required = status.required_hours
        worked = status.worked_hours
        remaining_hours = max(0, required - worked)
        remaining_secs = remaining_hours * 3600
        h = int(remaining_secs // 3600)
        m = int((remaining_secs % 3600) // 60)

        # 决定显示文本
        if remaining_secs <= 0:
            icon_text = f"{worked:.1f}h"
        elif h > 0:
            icon_text = f"{h}h"
        else:
            icon_text = f"{m}m"

        # 绘制图标
        pixmap = QtGui.QPixmap(56, 44)
        pixmap.setDevicePixelRatio(2.0)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        font = QtGui.QFont()
        font.setFamily("PingFang SC")
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.drawText(QtCore.QRect(0, 0, 28, 22), QtCore.Qt.AlignCenter, icon_text)
        painter.end()

        self.tray.setIcon(QtGui.QIcon(pixmap))

    def on_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        """托盘图标被点击时触发。

        左键单击 → 显示工时预览弹窗（非阻塞）。
        右键单击 → 显示功能菜单。

        Args:
            reason: 激活原因枚举
        """
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            # 左键 → 时长卡
            self._show_popup()
        elif reason == QtWidgets.QSystemTrayIcon.Context:
            # 右键 → 功能菜单
            self._tray_menu.popup(QtGui.QCursor.pos())

    def _show_popup(self) -> None:
        """在托盘图标位置显示工时预览弹窗（非阻塞方式）。

        使用 popup() 代替 exec_()，避免模态阻塞导致快速多次点击时卡死。
        每次弹出前销毁旧菜单，确保同时只有一个弹窗存在。
        """
        # 销毁旧菜单（如果存在）
        if self._tray_popup_menu is not None:
            self._tray_popup_menu.deleteLater()
            self._tray_popup_menu = None

        status = self._stats.get_today_status()

        menu = QtWidgets.QMenu(self._parent)
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        t = get_theme()
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: {t["card"]};
                border: 1px solid {t["stroke"]};
                border-radius: 12px;
                padding: 16px;
                min-width: 200px;
            }}
            QMenu::item {{
                padding: 4px 0;
                color: {t["main"]};
                font-size: 14px;
                background: transparent;
            }}
            QMenu::item:disabled {{ color: {t["main"]}; }}
            QMenu::separator {{ height: 1px; background: {t["div"]}; margin: 8px 0; }}
            QLabel {{
                background: transparent;
                color: {t["main"]};
            }}
            QProgressBar {{
                background-color: {t["track"]};
                border: none;
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
            }}
            QProgressBar::chunk {{
                background-color: {t["primary"]};
                border-radius: 4px;
            }}
        """
        )

        # 菜单关闭后自动清理引用
        menu.aboutToHide.connect(self._on_popup_hidden)

        if not status.has_started:
            act = menu.addAction("尚未上班")
            act.setEnabled(False)
            self._tray_popup_menu = menu
            menu.popup(QtGui.QCursor.pos())
            return

        required = status.required_hours
        worked = status.worked_hours

        # 构建弹窗内容
        widget_action = QtWidgets.QWidgetAction(menu)
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        worked_lbl = QtWidgets.QLabel(f"已工作  {worked:.1f}h")
        worked_lbl.setObjectName("TrayWorked")
        layout.addWidget(worked_lbl)

        bar = QtWidgets.QProgressBar()
        bar.setTextVisible(False)
        self._style_progress_bar(bar, worked, required)
        layout.addWidget(bar)

        pct = int(worked / required * 100) if required > 0 else 0
        pct_lbl = QtWidgets.QLabel(f"{pct}% / {required:.1f}h")
        pct_lbl.setObjectName("TrayPct")
        layout.addWidget(pct_lbl)

        layout.addSpacing(4)

        eta_lbl: QtWidgets.QLabel | None = None
        if status.end_time:
            remaining_lbl = QtWidgets.QLabel(f"已下班  工时 {worked:.1f}h")
            remaining_lbl.setObjectName("TrayOff")
        else:
            remaining = max(0, required - worked)
            rh = int(remaining)
            rm = int((remaining - rh) * 60)
            eta = datetime.now() + timedelta(hours=remaining)
            eta_lbl = QtWidgets.QLabel(f"预计下班 {eta.strftime('%H:%M')}")
            eta_lbl.setObjectName("TrayETA")
            if remaining <= 0:
                remaining_lbl = QtWidgets.QLabel("已达标，可以下班啦")
                remaining_lbl.setObjectName("TrayReached")
            else:
                remaining_lbl = QtWidgets.QLabel(f"距下班还有 {rh}小时{rm}分钟")
                remaining_lbl.setObjectName("TrayRemaining")

        layout.addWidget(remaining_lbl)
        if eta_lbl is not None and not status.end_time:
            layout.addWidget(eta_lbl)

        widget_action.setDefaultWidget(widget)
        menu.addAction(widget_action)

        # 非阻塞弹出
        self._tray_popup_menu = menu
        menu.popup(QtGui.QCursor.pos())

    def _on_popup_hidden(self) -> None:
        """托盘弹窗关闭后清理引用。"""
        self._tray_popup_menu = None

    def hide(self) -> None:
        """隐藏托盘图标（退出时调用）。"""
        self.tray.hide()

    @staticmethod
    def _style_progress_bar(bar: QtWidgets.QProgressBar, worked: float, required: float) -> None:
        """统一设置进度条：按 worked/required 百分比填充，>=100% 变绿，钳制到满格。"""
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
