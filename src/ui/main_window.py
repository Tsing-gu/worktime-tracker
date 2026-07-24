# -*- coding: utf-8 -*-
"""
main_window - 主窗口
======================

工时计算器的主界面，包含:
    - 今日概览（日期、上班时间、当前工时、进度条）
    - 本周 / 本月统计卡片
    - 功能按钮（设置 / 日历 / 请假 / 导出）
    - 系统托盘图标（菜单栏驻留 + 点击弹窗）
    - 30 秒定时轮询（驱动 tracker + 刷新 UI）

架构关系:
    MainWindow 只依赖 WorktimeService，不直接操作 database/tracker/calculator。

版本: 0.4.2
"""

import sys
import os
from datetime import datetime, date, timedelta

from PySide6 import QtWidgets, QtCore, QtGui

from src.config import (
    SETTING_DAILY_REQUIRED_HOURS,
    SETTING_NOTIFY_ON_TARGET,
    SETTING_NOTIFY_ON_OFF,
    SETTING_HOLIDAY_AUTO_EXCLUDE,
    POLL_INTERVAL_MS,
)
from src.services.worktime_service import WorktimeService
from src.services import notification_service
from src.services.update_service import UpdateService
from src.utils.paths import resource_path
from src.core.date_utils import compute_work_date
from src.ui.theme import get_theme
from src.ui.settings_dialog import SettingsDialog
from src.ui.calendar_dialog import CalendarHistoryDialog
from src.ui.leave_dialog import LeaveDialog
from src.ui.confirm_dialog import ConfirmYesterdayDialog
from src.ui.update_dialog import UpdateConfirmDialog, UpdateProgressDialog
from src.ui.edit_start_dialog import EditStartDialog


class MainWindow(QtWidgets.QMainWindow):
    """
    工时计算器主窗口。

    管理以下功能:
        - UI 初始化与刷新
        - 30 秒定时器驱动轮询
        - 系统托盘图标（菜单栏驻留 + 弹窗预览）
        - 次日确认弹窗检查
        - 手动下班 / 修改上班 / 设置 / 日历 / 请假 / 导出

    Attributes:
        service:  WorktimeService 实例，唯一的业务层入口
        tracker:   WorkTracker 实例（通过 service 间接管理）
        timer:     30 秒轮询定时器
        tray:      系统托盘图标
    """

    def __init__(self):
        """初始化主窗口：创建 service、初始化 UI/托盘/定时器、执行启动逻辑。"""
        super().__init__()
        self.setWindowTitle("工时计算器")
        self.setMinimumSize(640, 600)
        self.resize(680, 640)

        # 唯一的业务层入口
        self.service = WorktimeService()
        self.update_service = UpdateService(self.service.settings_repo)
        self._tray_popup_menu = None  # 当前时长卡菜单
        self._update_checking = False  # 防止重复检查

        self._init_ui()
        self._init_tray()
        self._init_timer()
        self._on_startup()

        from src.ui.theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_ui)

    # ─── UI 初始化 ─────────────────────────────────────────

    def _init_ui(self):
        """构建主界面所有可见元素。"""
        self.setWindowIcon(QtGui.QIcon(resource_path('resources/app.icns')))
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(28, 28, 28, 24)

        # ── 日期标题 ──
        today = compute_work_date(datetime.now())
        weekday_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        self.date_label = QtWidgets.QLabel(f"{today.year}年{today.month}月{today.day}日 {weekday_name}")
        self.date_label.setObjectName("DateLabel")
        self.date_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.date_label)

        # ── 今日状态卡片（按钮行 + 信息行 合并）──
        status_card = QtWidgets.QFrame()
        status_card.setObjectName("Card")
        status_layout = QtWidgets.QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(14)

        # 按钮行：修改上班（左）| 手动下班（右）
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(12)

        self.edit_start_btn = QtWidgets.QPushButton("修改上班")
        self.edit_start_btn.setObjectName("SecondaryBtn")
        self.edit_start_btn.setFixedHeight(32)
        self.edit_start_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.edit_start_btn.clicked.connect(self.on_edit_start)
        btn_row.addWidget(self.edit_start_btn)
        btn_row.addStretch()

        self.off_btn = QtWidgets.QPushButton("手动下班")
        self.off_btn.setObjectName("PrimaryBtn")
        self.off_btn.setFixedHeight(32)
        self.off_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.off_btn.clicked.connect(self.on_manual_off)
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
            ("设置", self.on_settings),
            ("日历", self.on_history),
            ("请假", self.on_leave),
            ("导出", self.on_export),
        ]:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedHeight(32)
            btn.setFocusPolicy(QtCore.Qt.NoFocus)
            btn.clicked.connect(handler)
            btn_box.addWidget(btn)
        layout.addLayout(btn_box)

    def _make_card(self, title: str) -> QtWidgets.QFrame:
        """
        创建一个统计卡片（周/月概览）。

        卡片包含标题、分隔线、4 行信息文本和 1 个进度条。

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

        self._card_labels = getattr(self, "_card_labels", {})
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

    # ─── 系统托盘 ──────────────────────────────────────────

    def _init_tray(self):
        """初始化菜单栏托盘图标及其右键菜单。"""
        self.tray = QtWidgets.QSystemTrayIcon()
        self.tray.setToolTip("工时计算器")
        icon = QtGui.QIcon(resource_path('resources/app.icns'))
        if icon.isNull():
            icon = self.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setVisible(True)

        # 右键菜单（不使用 setContextMenu，避免左键同时弹出系统菜单）
        self._tray_menu = QtWidgets.QMenu()
        act_show = self._tray_menu.addAction("打开主界面")
        act_show.triggered.connect(self.show_normal)
        act_off = self._tray_menu.addAction("手动下班")
        act_off.triggered.connect(self.on_manual_off)
        act_update = self._tray_menu.addAction("检查更新")
        act_update.triggered.connect(self.on_check_update)
        self._tray_menu.addSeparator()
        act_quit = self._tray_menu.addAction("退出")
        act_quit.triggered.connect(self.quit_app)

        # 点击托盘图标（左键弹时长卡，右键弹功能菜单）
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def _update_tray_icon(self, status):
        """
        更新托盘图标为剩余工时数字。

        未上班/已下班时不更新；上班中显示剩余小时数。

        Args:
            status: TodayStatus 对象
        """
        if not hasattr(self, 'tray') or not self.tray.isVisible():
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

    # ─── 定时器 ────────────────────────────────────────────

    def _init_timer(self):
        """初始化 30 秒轮询定时器。"""
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(POLL_INTERVAL_MS)

    # ─── 启动逻辑 ──────────────────────────────────────────

    def _on_startup(self):
        """程序启动时调用：初始化 service 并刷新 UI。"""
        self.service.init()
        self.refresh_ui()

    # ─── 窗口控制 ──────────────────────────────────────────

    def show_normal(self):
        """显示并激活主窗口（从隐藏/最小化状态恢复）。"""
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _style_progress_bar(self, bar: QtWidgets.QProgressBar, worked: float, required: float):
        """统一设置进度条：按 worked/required 百分比填充，>=100% 变绿，钳制到满格。

        内联样式同时设置 track 底色与 chunk 颜色，避免遮蔽全局 QProgressBar 样式导致底色透明。
        """
        t = get_theme()
        reached = required > 0 and worked >= required
        pct = int(worked / required * 100) if required > 0 else 0
        color = t['green'] if reached else t['primary']
        radius = "3px" if bar.objectName() == "CardBar" else "4px"
        bar.setMaximum(100)
        bar.setValue(min(100, pct))
        bar.setStyleSheet(
            f"QProgressBar {{ background-color: {t['track']}; border: none; border-radius: {radius}; }}"
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: {radius}; }}"
        )

    def on_tray_activated(self, reason):
        """
        托盘图标被点击时触发。

        左键单击 → 显示工时预览弹窗（非阻塞）。
        右键单击 → 显示功能菜单（打开主界面/手动下班/退出）。

        Args:
            reason: 激活原因枚举
        """
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            # 左键 → 时长卡
            self._show_tray_popup()
        elif reason == QtWidgets.QSystemTrayIcon.Context:
            # 右键 → 功能菜单
            self._tray_menu.popup(QtGui.QCursor.pos())

    def _show_tray_popup(self):
        """
        在托盘图标位置显示工时预览弹窗（非阻塞方式）。

        使用 popup() 代替 exec_()，避免模态阻塞导致快速多次点击时卡死。
        每次弹出前销毁旧菜单，确保同时只有一个弹窗存在。
        """
        # 销毁旧菜单（如果存在）
        if self._tray_popup_menu is not None:
            self._tray_popup_menu.deleteLater()
            self._tray_popup_menu = None

        status = self.service.get_today_status()

        menu = QtWidgets.QMenu(self)
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        t = get_theme()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {t['card']};
                border: 1px solid {t['stroke']};
                border-radius: 12px;
                padding: 16px;
                min-width: 200px;
            }}
            QMenu::item {{
                padding: 4px 0;
                color: {t['main']};
                font-size: 14px;
                background: transparent;
            }}
            QMenu::item:disabled {{ color: {t['main']}; }}
            QMenu::separator {{ height: 1px; background: {t['div']}; margin: 8px 0; }}
            QLabel {{
                background: transparent;
                color: {t['main']};
            }}
            QProgressBar {{
                background-color: {t['track']};
                border: none;
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
            }}
            QProgressBar::chunk {{
                background-color: {t['primary']};
                border-radius: 4px;
            }}
        """)

        # 菜单关闭后自动清理引用
        menu.aboutToHide.connect(self._on_tray_popup_hidden)

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

        if status.end_time:
            remaining_lbl = QtWidgets.QLabel(f"已下班  工时 {worked:.1f}h")
            remaining_lbl.setObjectName("TrayOff")
        else:
            from datetime import datetime as _dt, timedelta as _td
            remaining = max(0, required - worked)
            rh = int(remaining)
            rm = int((remaining - rh) * 60)
            eta = _dt.now() + _td(hours=remaining)
            eta_lbl = QtWidgets.QLabel(f"预计下班 {eta.strftime('%H:%M')}")
            eta_lbl.setObjectName("TrayETA")
            if remaining <= 0:
                remaining_lbl = QtWidgets.QLabel("已达标，可以下班啦")
                remaining_lbl.setObjectName("TrayReached")
            else:
                remaining_lbl = QtWidgets.QLabel(f"距下班还有 {rh}小时{rm}分钟")
                remaining_lbl.setObjectName("TrayRemaining")

        layout.addWidget(remaining_lbl)
        if not status.end_time:
            layout.addWidget(eta_lbl)

        widget_action.setDefaultWidget(widget)
        menu.addAction(widget_action)

        # 非阻塞弹出
        self._tray_popup_menu = menu
        menu.popup(QtGui.QCursor.pos())

    def _on_tray_popup_hidden(self):
        """托盘弹窗关闭后清理引用。"""
        self._tray_popup_menu = None

    # ─── 定时轮询回调 ─────────────────────────────────────

    def on_tick(self):
        """
        30 秒定时器回调。

        流程:
            1. 调用 service.poll_and_record() 执行轮询 + 持久化
            2. 根据返回事件发送通知（下班/达标/回来）
            3. 检查次日确认弹窗
            4. 刷新 UI
        """
        result = self.service.poll_and_record()

        # ── 下班通知 ──
        if result.event == "off":
            if self._get_setting_bool(SETTING_NOTIFY_ON_OFF, True):
                notification_service.notify_off_work(
                    result.off_time.strftime("%H:%M"), result.worked_hours
                )
        # ── 达标通知 ──
        elif result.event == "target_reached":
            if self._get_setting_bool(SETTING_NOTIFY_ON_TARGET, True):
                status = self.service.get_today_status()
                required = status.required_hours
                notification_service.notify_target_reached(result.worked_hours, required)
        # ── 下班后回来 → 弹窗确认恢复 ──
        elif result.event == "back":
            self._confirm_resume()

        # ── 先刷新 UI（含日期），确保跨天后界面立即更新 ──
        self.refresh_ui()

        # ── 再弹次日确认/更新检查（可能阻塞，放最后）──
        if self.service.should_check_yesterday():
            self._check_yesterday_confirm()
            self._check_update_after_confirm()

    def _confirm_resume(self):
        """
        下班后检测到用户回来活跃，弹窗确认是否恢复计时。

        确认 → 调用 service.resume_after_off() 清除下班记录，恢复"工作中"状态
        取消 → 保持下班状态不变
        """
        reply = QtWidgets.QMessageBox.question(
            self, "恢复计时",
            "检测到您已回来继续工作，是否恢复计时？\n\n"
            "确认 → 清除下班记录，继续追踪工时\n"
            "取消 → 保持当前下班状态",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.service.resume_after_off()
            self.refresh_ui()

    # ─── 手动检查更新 ──────────────────────────────────────

    def on_check_update(self):
        """托盘菜单「检查更新」手动触发。"""
        if self._update_checking:
            QtWidgets.QMessageBox.information(self, "检查更新", "正在检查中，请稍候...")
            return
        self._update_checking = True
        try:
            info = self.update_service.check_for_updates()
            self.update_service.mark_checked()
            if not info:
                QtWidgets.QMessageBox.information(self, "检查更新", "已是最新版本")
                return
            self._show_update_confirm(info)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "检查更新", f"检查失败：{e}")
        finally:
            self._update_checking = False

    def _check_update_after_confirm(self):
        """次日确认完成后自动检查更新（每天一次），有新版则弹更新确认窗。"""
        self.service.mark_yesterday_checked()
        try:
            info = self.update_service.check_for_updates()
            self.update_service.mark_checked()
            if info:
                self._show_update_confirm(info)
        except Exception as e:
            print(f"[Update] 自动检查失败：{e}")

    def _show_update_confirm(self, info):
        """弹出更新确认窗。"""
        dlg = UpdateConfirmDialog(info, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._download_and_install(info)

    def _download_and_install(self, info):
        """下载并安装更新。"""
        progress = UpdateProgressDialog(self)
        progress.show()
        self.update_service.reset_cancel()
        progress.set_cancel_callback(self.update_service.cancel_download)

        def on_progress(downloaded, total):
            # 通过 QMetaObject 在主线程更新 UI，避免跨线程操作 Qt 控件崩溃
            QtCore.QMetaObject.invokeMethod(progress, "update_progress",
                                            QtCore.Qt.QueuedConnection,
                                            QtCore.Q_ARG(int, downloaded),
                                            QtCore.Q_ARG(int, total))

        def worker():
            dmg_path = self.update_service.download_update(info.dmg_url, on_progress)
            # 检查是否被用户取消
            if progress.is_cancelled():
                QtCore.QMetaObject.invokeMethod(progress, "set_status",
                                                QtCore.Qt.QueuedConnection,
                                                QtCore.Q_ARG(str, "已取消下载"))
                QtCore.QMetaObject.invokeMethod(progress, "close",
                                                QtCore.Qt.QueuedConnection)
                return
            if not dmg_path or not self.update_service.verify_update(dmg_path, info.length):
                QtCore.QMetaObject.invokeMethod(progress, "set_status",
                                                QtCore.Qt.QueuedConnection,
                                                QtCore.Q_ARG(str, "下载失败，请稍后重试"))
                return
            QtCore.QMetaObject.invokeMethod(progress, "set_status",
                                            QtCore.Qt.QueuedConnection,
                                            QtCore.Q_ARG(str, "下载完成，正在安装并重启..."))
            ok = self.update_service.install_and_restart(dmg_path)
            if not ok:
                QtCore.QMetaObject.invokeMethod(progress, "set_status",
                                                QtCore.Qt.QueuedConnection,
                                                QtCore.Q_ARG(str, "无法自动安装（开发环境）"))
                return
            # 安装脚本已启动，退出主进程让脚本替换 .app 并重启
            QtCore.QMetaObject.invokeMethod(QtWidgets.QApplication.instance(), "quit",
                                            QtCore.Qt.QueuedConnection)

        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _check_yesterday_confirm(self):
        """
        检查是否需要弹出次日确认弹窗。

        通过 service.check_yesterday() 获取待确认的前一工作日记录，
        弹出 ConfirmYesterdayDialog 供用户确认或修改。
        """
        result = self.service.check_yesterday()
        if result is None:
            return

        prev, daily = result
        required = self.service.get_required_hours()
        dialog = ConfirmYesterdayDialog(prev, daily, required, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            end_time = dialog.get_end_time()
            self.service.confirm_yesterday(prev, end_time)
        else:
            self.service.skip_yesterday(prev)
        self.service.mark_yesterday_checked()

    # ─── UI 刷新 ──────────────────────────────────────────

    def refresh_ui(self):
        """刷新主界面所有实时数据：今日状态 + 周/月统计卡片 + 托盘图标。"""
        # ── 日期（跨天后自动更新）──
        today = compute_work_date(datetime.now())
        weekday_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        self.date_label.setText(f"{today.year}年{today.month}月{today.day}日 {weekday_name}")

        status = self.service.get_today_status()

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
        if status.start_time and not status.end_time:
            required = status.required_hours
            remaining = max(0, required - status.worked_hours)
            from datetime import datetime as _dt, timedelta as _td
            eta = _dt.now() + _td(hours=remaining)
            self.eta_label.setText(eta.strftime("%H:%M"))
        elif status.end_time:
            self.eta_label.setText("已下班")
        else:
            self.eta_label.setText("--:--")

        # ── 托盘图标 ──
        self._update_tray_icon(status)

        # ── 本期卡片 ──
        period = self.service.get_period_stats()
        if period.is_rest:
            self._card_labels["本期概览_line1"].setText("休息中")
            self._card_labels["本期概览_line2"].setText("")
            self._card_labels["本期概览_line3"].setText("")
            bar = self._card_labels["本期概览_bar"]
            bar.setStyleSheet("")
            bar.setMaximum(100)
            bar.setValue(0)
        else:
            self._card_labels["本期概览_line1"].setText(f"已工作 {period.worked_days}天 / {period.total_workdays}天")
            self._card_labels["本期概览_line2"].setText(f"累计 {period.worked_hours:.1f}h / 目标 {period.target_hours:.0f}h")
            if period.remaining_days > 1:
                self._card_labels["本期概览_line3"].setText(f"日均 {period.daily_avg:.1f}h, 剩余{period.remaining_days}天 每天需{period.remaining_per_day:.1f}h达标")
            else:
                left = max(0, period.target_hours - period.worked_hours)
                self._card_labels["本期概览_line3"].setText(f"今天干完就放假啦！还剩{left:.1f}h")
            bar = self._card_labels["本期概览_bar"]
            self._style_progress_bar(bar, period.worked_hours, period.target_hours)

        # ── 本月卡片 ──
        month = self.service.get_month_stats()
        self._card_labels["本月概览_line1"].setText(f"已工作 {month.worked_days}天 / {month.total_workdays}天")
        self._card_labels["本月概览_line2"].setText(f"累计 {month.worked_hours:.1f}h / 目标 {month.target_hours:.0f}h")
        if month.remaining_days > 1:
            self._card_labels["本月概览_line3"].setText(f"日均 {month.daily_avg:.1f}h, 剩余{month.remaining_days}天 每天需{month.remaining_per_day:.1f}h达标")
        else:
            left = max(0, month.target_hours - month.worked_hours)
            self._card_labels["本月概览_line3"].setText(f"今天干完就放假啦！还剩{left:.1f}h")
        bar2 = self._card_labels["本月概览_bar"]
        self._style_progress_bar(bar2, month.worked_hours, month.target_hours)

    # ─── 事件处理 ──────────────────────────────────────────

    def on_edit_start(self):
        """修改今日上班时间：弹出自定义对话框，支持手动输入或从 pmset 读取。"""
        status = self.service.get_today_status()
        current_start = status.start_time
        current_str = current_start.strftime("%H:%M") if current_start else ""

        dialog = EditStartDialog(current_str, self.service, self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        new_str = dialog.get_time_str()
        if not new_str:
            return

        try:
            new_start = self.service.edit_start_time(new_str)
            self.refresh_ui()
            QtWidgets.QMessageBox.information(self, "已修改", f"上班时间已更新为 {new_start.strftime('%H:%M')}")
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "格式错误", str(e))

    def on_manual_off(self):
        """手动下班：弹窗确认后通过 service.manual_off() 记录。"""
        status = self.service.get_today_status()
        if not status.has_started:
            QtWidgets.QMessageBox.information(self, "提示", "今天还没有上班记录，无法下班")
            return
        if status.end_time:
            QtWidgets.QMessageBox.information(self, "提示", "今天已经下班了")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "确认下班",
            f"当前时间：{datetime.now().strftime('%H:%M')}\n"
            f"今日已工作：{status.worked_hours:.1f} 小时"
            f"{'  已达标' if status.is_target_reached else ''}\n\n"
            f"确认以当前时间记录下班？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.Yes:
            result = self.service.manual_off()
            if result.event == "manual_off":
                QtWidgets.QMessageBox.information(
                    self, "已下班",
                    f"下班时间：{result.off_time.strftime('%H:%M')}\n"
                    f"今日工时：{result.worked_hours:.2f} 小时",
                )
                self.refresh_ui()

    def on_settings(self):
        """打开设置弹窗，确认后保存设置。"""
        dialog = SettingsDialog(self.service.get_settings(), self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.service.update_settings(dialog.get_values())
            self.refresh_ui()

    def on_history(self):
        """打开日历历史弹窗。"""
        dialog = CalendarHistoryDialog(self, service=self.service)
        dialog.exec()

    def on_leave(self):
        """打开请假弹窗，确认后通过 service 标记请假。"""
        today = compute_work_date(datetime.now())
        dialog = LeaveDialog(self, default_date=today)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            leave_date = dialog.get_date()
            leave_type = dialog.get_leave_type()
            self.service.mark_leave(leave_date, leave_type)
            self.refresh_ui()

    def on_export(self):
        """导出本月数据为 Excel。"""
        today = compute_work_date(datetime.now())
        if today.month == 12:
            start = date(today.year, 12, 1)
            end = date(today.year, 12, 31)
        else:
            start = date(today.year, today.month, 1)
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("导出")
        dlg.setMinimumWidth(300)
        dlg_layout = QtWidgets.QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(24, 20, 24, 16)
        dlg_layout.setSpacing(12)

        dlg_layout.addWidget(QtWidgets.QLabel(f"导出本月数据（{start} ~ {end}）"))

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setFixedSize(96, 32)
        cancel_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        export_btn = QtWidgets.QPushButton("导出 Excel")
        export_btn.setObjectName("PrimaryBtn")
        export_btn.setFixedSize(96, 32)
        export_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        export_btn.clicked.connect(lambda: dlg.done(1))
        btn_row.addWidget(export_btn)
        dlg_layout.addLayout(btn_row)

        if dlg.exec() != 1:
            return

        exporter = self.service.get_exporter()
        path = exporter.to_excel(start, end)
        QtWidgets.QMessageBox.information(self, "导出成功", f"文件已保存到：\n{path}")

    # ─── 窗口关闭与退出 ────────────────────────────────────

    def closeEvent(self, event):
        """
        关闭窗口时不退出程序，转入菜单栏托盘继续运行。

        Args:
            event: 关闭事件
        """
        event.ignore()
        self.hide()

    def quit_app(self):
        """退出程序：停止定时器 + 隐藏托盘 + 退出应用。"""
        self.timer.stop()
        self.tray.hide()
        QtWidgets.QApplication.quit()

    # ─── 辅助方法 ──────────────────────────────────────────

    def _get_setting(self, key: str, default: str = "") -> str:
        """读取设置值的快捷方法。"""
        return self.service.get_setting(key, default)

    def _get_setting_bool(self, key: str, default: bool = False) -> bool:
        """读取布尔型设置值的快捷方法。"""
        return self._get_setting(key, "1" if default else "0") == "1"
