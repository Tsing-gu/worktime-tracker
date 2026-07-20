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

from src.data import database
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
)


class SettingsDialog(QtWidgets.QDialog):
    """
    设置弹窗对话框。

    从 database 读取当前设置值填充表单，
    用户确认后通过 get_values() 返回更新值字典。
    """

    def __init__(self, parent=None):
        """
        初始化设置弹窗，从 DB 读取当前值填充控件。

        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(380)

        layout = QtWidgets.QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 16)

        # ── 每日工时要求 ──
        self.daily_hours = QtWidgets.QDoubleSpinBox()
        self.daily_hours.setRange(1, 24)
        self.daily_hours.setSingleStep(0.5)
        self.daily_hours.setValue(float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0")))
        layout.addRow("每日工时要求（小时）", self.daily_hours)

        # ── 每周工作天数 ──
        self.weekly_days = QtWidgets.QSpinBox()
        self.weekly_days.setRange(1, 7)
        self.weekly_days.setValue(int(database.get_setting(SETTING_WEEKLY_WORK_DAYS, "5")))
        layout.addRow("每周工作天数", self.weekly_days)

        # ── 下班判定：离开等待时长 ──
        self.off_threshold = QtWidgets.QSpinBox()
        self.off_threshold.setRange(5, 480)
        self.off_threshold.setSuffix(" 分钟")
        self.off_threshold.setValue(int(database.get_setting(SETTING_OFF_THRESHOLD_MINUTES, "60")))
        layout.addRow("下班判定：离开等待时长", self.off_threshold)

        # ── 下班判定：时间下限 ──
        self.off_floor = QtWidgets.QTimeEdit()
        floor_str = database.get_setting(SETTING_OFF_TIME_FLOOR, "19:00")
        h, m = map(int, floor_str.split(":"))
        self.off_floor.setTime(QtCore.QTime(h, m))
        layout.addRow("下班判定：时间下限", self.off_floor)

        # ── 上班检测起始时间 ──
        self.work_start_floor = QtWidgets.QTimeEdit()
        start_floor_str = database.get_setting(SETTING_WORK_START_FLOOR, "06:00")
        sh, sm = map(int, start_floor_str.split(":"))
        self.work_start_floor.setTime(QtCore.QTime(sh, sm))
        layout.addRow("上班检测起始时间", self.work_start_floor)

        # ── 通知开关 ──
        self.notify_target = QtWidgets.QCheckBox("达到每日工时要求时弹窗提醒")
        self.notify_target.setChecked(database.get_setting(SETTING_NOTIFY_ON_TARGET, "1") == "1")
        layout.addRow(self.notify_target)

        self.notify_off = QtWidgets.QCheckBox("检测到下班时系统通知")
        self.notify_off.setChecked(database.get_setting(SETTING_NOTIFY_ON_OFF, "1") == "1")
        layout.addRow(self.notify_off)

        # ── 开机自启动 ──
        self.auto_start = QtWidgets.QCheckBox("开机自动启动")
        self.auto_start.setChecked(database.get_setting(SETTING_AUTO_START, "0") == "1")
        layout.addRow(self.auto_start)

        # ── 节假日自动获取 ──
        self.holiday_auto = QtWidgets.QCheckBox("自动获取节假日")
        self.holiday_auto.setChecked(database.get_setting(SETTING_HOLIDAY_AUTO_EXCLUDE, "1") == "1")
        layout.addRow(self.holiday_auto)

        # ── 确认/取消按钮 ──
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

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
        }
