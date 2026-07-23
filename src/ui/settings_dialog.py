# -*- coding: utf-8 -*-
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

from PySide6 import QtWidgets, QtCore

from src.config import (
    SETTING_DAILY_REQUIRED_HOURS,
    SETTING_WEEKLY_WORK_DAYS,
    SETTING_OFF_THRESHOLD_MINUTES,
    SETTING_OFF_TIME_FLOOR,
    SETTING_WORK_START_FLOOR,
    SETTING_NOTIFY_ON_TARGET,
    SETTING_NOTIFY_ON_OFF,
    SETTING_AUTO_START,
    SETTING_HOLIDAY_AUTO_EXCLUDE,
    SETTING_OFFICE_NETWORK_DOMAIN,
    SETTING_ONLY_OFFICE_TIME,
)
from src.ui.theme import get_theme


class SettingsDialog(QtWidgets.QDialog):
    """
    设置弹窗对话框。

    从传入的 settings dict 读取当前设置值填充表单，
    用户确认后通过 get_values() 返回更新值字典。
    """

    def __init__(self, settings: dict, parent=None):
        """
        初始化设置弹窗，从 settings dict 读取当前值填充控件。

        Args:
            settings: 当前设置字典 {key: value}
            parent:   父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(24, 24, 24, 16)

        # ── 工时设置组 ──
        work_group = QtWidgets.QGroupBox("工时设置")
        work_form = QtWidgets.QFormLayout(work_group)
        work_form.setSpacing(10)

        self.daily_hours = QtWidgets.QDoubleSpinBox()
        self.daily_hours.setFocusPolicy(QtCore.Qt.NoFocus)
        self.daily_hours.setRange(1, 24)
        self.daily_hours.setSingleStep(0.5)
        self.daily_hours.setValue(float(settings.get(SETTING_DAILY_REQUIRED_HOURS, "8.0")))
        work_form.addRow("每日工时要求（小时）", self.daily_hours)

        self.weekly_days = QtWidgets.QSpinBox()
        self.weekly_days.setFocusPolicy(QtCore.Qt.NoFocus)
        self.weekly_days.setRange(1, 7)
        self.weekly_days.setValue(int(settings.get(SETTING_WEEKLY_WORK_DAYS, "5")))
        work_form.addRow("每周工作天数", self.weekly_days)

        self.off_threshold = QtWidgets.QSpinBox()
        self.off_threshold.setFocusPolicy(QtCore.Qt.NoFocus)
        self.off_threshold.setRange(5, 480)
        self.off_threshold.setSuffix(" 分钟")
        self.off_threshold.setValue(int(settings.get(SETTING_OFF_THRESHOLD_MINUTES, "60")))
        work_form.addRow("下班判定：离开等待时长", self.off_threshold)

        self.off_floor = QtWidgets.QTimeEdit()
        self.off_floor.setFocusPolicy(QtCore.Qt.NoFocus)
        floor_str = settings.get(SETTING_OFF_TIME_FLOOR, "19:00")
        h, m = map(int, floor_str.split(":"))
        self.off_floor.setTime(QtCore.QTime(h, m))
        work_form.addRow("下班判定：时间下限", self.off_floor)

        self.work_start_floor = QtWidgets.QTimeEdit()
        self.work_start_floor.setFocusPolicy(QtCore.Qt.NoFocus)
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
        other_form.setSpacing(10)

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
        self.record_office_btn = QtWidgets.QPushButton("记录当前网络为办公网络")
        self.record_office_btn.clicked.connect(self._on_record_office)
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
        self.check_update_btn = QtWidgets.QPushButton("立即检查更新")
        self.check_update_btn.clicked.connect(self._on_check_update)
        bottom_bar.addWidget(self.check_update_btn)
        main_layout.addLayout(bottom_bar)

        # ── 确认/取消按钮 ──
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setFocusPolicy(QtCore.Qt.NoFocus)
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setFocusPolicy(QtCore.Qt.NoFocus)
        self.check_update_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.record_office_btn.setFocusPolicy(QtCore.Qt.NoFocus)

        # ── 确认/取消按钮 ──
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

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

    def _on_only_office_toggled(self, state):
        """勾选「只记录在公司时间」时，若办公网络未设置则提示并阻止勾选。"""
        if state == QtCore.Qt.Checked and not self._office_domain:
            QtWidgets.QMessageBox.warning(
                self, "无法启用",
                "请先在下方「办公网络」处记录办公网络，才能启用此功能。"
            )
            self.only_office.setCheckState(QtCore.Qt.Unchecked)

    def _on_check_update(self):
        """立即检查更新，调用父窗口（MainWindow）的更新逻辑。"""
        parent = self.parent()
        if parent and hasattr(parent, "on_check_update"):
            self.close()
            parent.on_check_update()
        else:
            QtWidgets.QMessageBox.information(self, "检查更新", "请在主界面托盘菜单中检查更新")

    def _on_record_office(self):
        """检测当前网络的 DHCP domain_search，记录为办公网络域名。"""
        from src.utils.system import get_network_status

        status = get_network_status()
        domain = status.get("domain", "")
        if not domain:
            QtWidgets.QMessageBox.warning(self, "记录失败", "未能检测到当前网络的搜索域，请确保已连接 WiFi。")
            return
        self.office_domain_label.setText(domain)
        self.office_domain_label.setStyleSheet(f"color: {get_theme()['green']};")
        self._office_domain = domain
        QtWidgets.QMessageBox.information(
            self, "已记录", f"已将「{domain}」记录为办公网络域名。\n点击「确定」保存设置后生效。"
        )
