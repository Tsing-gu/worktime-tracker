"""
settings_dialog - 设置弹窗
=============================

提供用户可配置项的编辑界面：
    - 每日工时要求
    - 每周工作天数
    - 下班判定阈值（离开等待时长 + 时间下限）
    - 上班检测起始时间
    - 通知开关
    - 开机自启动
    - 节假日自动获取

版本: 0.4.2
"""

from collections.abc import Callable

from PySide6 import QtCore, QtWidgets

from src.app.runtime import start_managed_thread
from src.config import (
    SETTING_AUTO_START,
    SETTING_DAILY_REQUIRED_HOURS,
    SETTING_HOLIDAY_AUTO_EXCLUDE,
    SETTING_NOTIFY_ON_OFF,
    SETTING_NOTIFY_ON_TARGET,
    SETTING_OFF_THRESHOLD_MINUTES,
    SETTING_OFF_TIME_FLOOR,
    SETTING_OFFICE_NETWORK_DOMAIN,
    SETTING_ONLY_OFFICE_TIME,
    SETTING_WEEKLY_WORK_DAYS,
    SETTING_WORK_START_FLOOR,
)
from src.ui.components.dialog_buttons import make_dialog_button
from src.ui.theme import repolish
from src.ui.theme.metrics import (
    DIALOG_BOTTOM_MARGIN,
    DIALOG_MARGIN,
    FORM_SPACING,
    MEDIUM_DIALOG_WIDTH,
)


class SettingsDialogUI(QtWidgets.QDialog):
    """
    设置弹窗对话框。

    从传入的 settings dict 读取当前设置值填充表单，
    用户确认后通过 get_values() 返回更新值字典。
    """

    @staticmethod
    def _msg(
        icon_name: str,
        parent: QtWidgets.QWidget,
        title: str,
        text: str,
    ) -> None:
        """非模态自定义提示框（用 make_dialog_button，避免 QMessageBox 焦点链问题）。"""
        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(320)
        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setContentsMargins(DIALOG_MARGIN, 20, DIALOG_MARGIN, DIALOG_BOTTOM_MARGIN)
        layout.setSpacing(12)

        label = QtWidgets.QLabel(text)
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

    @staticmethod
    def _msg_info(parent: QtWidgets.QWidget, title: str, text: str) -> None:
        SettingsDialogUI._msg("info", parent, title, text)

    @staticmethod
    def _msg_warn(parent: QtWidgets.QWidget, title: str, text: str) -> None:
        SettingsDialogUI._msg("warning", parent, title, text)

    def __init__(
        self,
        settings: dict,
        parent: QtWidgets.QWidget | None = None,
        on_check_update: Callable[[], None] | None = None,
    ) -> None:
        """
        初始化设置弹窗，从 settings dict 读取当前值填充控件。

        Args:
            settings:        当前设置字典 {key: value}
            parent:          父窗口
            on_check_update: 检查更新回调（由 DialogCoordinator 注入 UpdateFlowController）
        """
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(MEDIUM_DIALOG_WIDTH)
        self._on_check_update_cb = on_check_update

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(
            DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_BOTTOM_MARGIN
        )

        # ── 工时设置组 ──
        work_group = QtWidgets.QGroupBox("工时设置")
        work_form = QtWidgets.QFormLayout(work_group)
        work_form.setSpacing(FORM_SPACING)

        self.daily_hours = QtWidgets.QDoubleSpinBox()
        self.daily_hours.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.daily_hours.setRange(1, 24)
        self.daily_hours.setSingleStep(0.5)
        self.daily_hours.setValue(float(settings.get(SETTING_DAILY_REQUIRED_HOURS, "8.0")))
        work_form.addRow("每日工时要求（小时）", self.daily_hours)

        self.weekly_days = QtWidgets.QSpinBox()
        self.weekly_days.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.weekly_days.setRange(1, 7)
        self.weekly_days.setValue(int(settings.get(SETTING_WEEKLY_WORK_DAYS, "5")))
        work_form.addRow("每周工作天数", self.weekly_days)

        self.off_threshold = QtWidgets.QSpinBox()
        self.off_threshold.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.off_threshold.setRange(5, 480)
        self.off_threshold.setSuffix(" 分钟")
        self.off_threshold.setValue(int(settings.get(SETTING_OFF_THRESHOLD_MINUTES, "60")))
        work_form.addRow("下班判定：离开等待时长", self.off_threshold)

        self.off_floor = QtWidgets.QTimeEdit()
        self.off_floor.setDisplayFormat("HH:mm")
        self.off_floor.setFocusPolicy(QtCore.Qt.ClickFocus)
        floor_str = settings.get(SETTING_OFF_TIME_FLOOR, "19:00")
        h, m = map(int, floor_str.split(":"))
        self.off_floor.setTime(QtCore.QTime(h, m))
        work_form.addRow("下班判定：时间下限", self.off_floor)

        self.work_start_floor = QtWidgets.QTimeEdit()
        self.work_start_floor.setDisplayFormat("HH:mm")
        self.work_start_floor.setFocusPolicy(QtCore.Qt.ClickFocus)
        start_floor_str = settings.get(SETTING_WORK_START_FLOOR, "06:00")
        sh, sm = map(int, start_floor_str.split(":"))
        self.work_start_floor.setTime(QtCore.QTime(sh, sm))
        work_form.addRow("上班检测起始时间", self.work_start_floor)
        main_layout.addWidget(work_group)

        # ── 通知组 ──
        notify_group = QtWidgets.QGroupBox("通知")
        notify_layout = QtWidgets.QVBoxLayout(notify_group)
        notify_layout.setSpacing(8)

        self.notify_target = QtWidgets.QCheckBox("达到每日工时要求时弹窗提醒")
        self.notify_target.setChecked(settings.get(SETTING_NOTIFY_ON_TARGET, "1") == "1")
        notify_layout.addWidget(self.notify_target)

        self.notify_off = QtWidgets.QCheckBox("检测到下班时系统通知")
        self.notify_off.setChecked(settings.get(SETTING_NOTIFY_ON_OFF, "1") == "1")
        notify_layout.addWidget(self.notify_off)
        main_layout.addWidget(notify_group)

        # ── 其他组 ──
        other_group = QtWidgets.QGroupBox("其他")
        other_form = QtWidgets.QFormLayout(other_group)
        other_form.setSpacing(FORM_SPACING)

        self.auto_start = QtWidgets.QCheckBox("开机自动启动")
        self.auto_start.setChecked(settings.get(SETTING_AUTO_START, "0") == "1")
        other_form.addRow(self.auto_start)

        self.holiday_auto = QtWidgets.QCheckBox("自动获取节假日")
        self.holiday_auto.setChecked(settings.get(SETTING_HOLIDAY_AUTO_EXCLUDE, "1") == "1")
        other_form.addRow(self.holiday_auto)

        self.only_office = QtWidgets.QCheckBox("只记录在公司时间（需先记录办公网络）")
        self.only_office.setChecked(settings.get(SETTING_ONLY_OFFICE_TIME, "1") == "1")
        self.only_office.stateChanged.connect(self._on_only_office_toggled)
        other_form.addRow(self.only_office)

        self._office_domain = settings.get(SETTING_OFFICE_NETWORK_DOMAIN, "")
        office_layout = QtWidgets.QHBoxLayout()
        self.office_domain_label = QtWidgets.QLabel(self._office_domain or "未设置")
        self.office_domain_label.setObjectName("OfficeDomain")
        self.office_domain_label.setProperty(
            "state", "configured" if self._office_domain else "empty"
        )
        self.record_office_btn = make_dialog_button(
            "记录当前网络为办公网络", "secondary", self._on_record_office
        )
        office_layout.addWidget(self.office_domain_label)
        office_layout.addWidget(self.record_office_btn)
        other_form.addRow("办公网络", office_layout)
        main_layout.addWidget(other_group)

        # ── 版本号 + 检查更新 ──
        bottom_bar = QtWidgets.QHBoxLayout()
        from src.utils.version import get_version

        version_label = QtWidgets.QLabel(f"工时计算器 v{get_version()}")
        version_label.setObjectName("VersionLabel")
        bottom_bar.addWidget(version_label)
        bottom_bar.addStretch()
        self.check_update_btn = make_dialog_button(
            "立即检查更新", "secondary", self._on_check_update
        )
        bottom_bar.addWidget(self.check_update_btn)
        main_layout.addLayout(bottom_bar)

        # ── 确认/取消按钮（手动创建两个实例，避免 QDialogButtonBox 焦点链问题）──
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = make_dialog_button("取消", "secondary", self.reject)
        ok_btn = make_dialog_button("确定", "primary", self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        main_layout.addLayout(btn_layout)

    def get_values(self) -> dict:
        """
        获取用户填写的新设置值。

        Returns:
            {setting_key: value_str} 字典
        """
        return {
            SETTING_DAILY_REQUIRED_HOURS: str(self.daily_hours.value()),
            SETTING_WEEKLY_WORK_DAYS: str(self.weekly_days.value()),
            SETTING_OFF_THRESHOLD_MINUTES: str(self.off_threshold.value()),
            SETTING_OFF_TIME_FLOOR: self.off_floor.time().toString("HH:mm"),
            SETTING_WORK_START_FLOOR: self.work_start_floor.time().toString("HH:mm"),
            SETTING_NOTIFY_ON_TARGET: "1" if self.notify_target.isChecked() else "0",
            SETTING_NOTIFY_ON_OFF: "1" if self.notify_off.isChecked() else "0",
            SETTING_AUTO_START: "1" if self.auto_start.isChecked() else "0",
            SETTING_HOLIDAY_AUTO_EXCLUDE: "1" if self.holiday_auto.isChecked() else "0",
            SETTING_ONLY_OFFICE_TIME: "1" if self.only_office.isChecked() else "0",
            SETTING_OFFICE_NETWORK_DOMAIN: self._office_domain,
        }

    def _on_only_office_toggled(self, state: QtCore.Qt.CheckState) -> None:
        """勾选「只记录在公司时间」时，若办公网络未设置则提示并阻止勾选。"""
        if state == QtCore.Qt.Checked and not self._office_domain:
            self._msg_warn(
                self, "无法启用", "请先在下方「办公网络」处记录办公网络，才能启用此功能。"
            )
            self.only_office.setCheckState(QtCore.Qt.Unchecked)

    def _on_check_update(self) -> None:
        """立即检查更新，通过注入的回调通知 UpdateFlowController。"""
        if self._on_check_update_cb is not None:
            self.close()
            self._on_check_update_cb()
        else:
            self._msg_info(self, "检查更新", "请在主界面托盘菜单中检查更新")

    def _on_record_office(self) -> None:
        """检测当前网络的 DHCP domain_search，记录为办公网络域名（子线程执行避免阻塞）。"""
        self.record_office_btn.setEnabled(False)
        self.record_office_btn.setText("检测中...")

        def worker() -> None:
            from src.utils.system import get_network_status

            status = get_network_status()
            domain = status.get("domain", "")
            QtCore.QMetaObject.invokeMethod(
                self,
                "_on_record_office_result",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(str, domain),
            )

        start_managed_thread(worker, name="record-office-network")

    @QtCore.Slot(str)
    def _on_record_office_result(self, domain: str) -> None:
        """网络检测完成，在主线程处理结果。"""
        self.record_office_btn.setEnabled(True)
        self.record_office_btn.setText("记录当前网络为办公网络")
        if not domain:
            self._msg_warn(self, "记录失败", "未能检测到当前网络的搜索域，请确保已连接 WiFi。")
            return
        self.office_domain_label.setText(domain)
        self.office_domain_label.setProperty("state", "configured")
        repolish(self.office_domain_label)
        self._office_domain = domain
        self._msg_info(
            self, "已记录", f"已将「{domain}」记录为办公网络域名。\n点击「确定」保存设置后生效。"
        )
