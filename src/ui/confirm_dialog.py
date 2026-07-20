# -*- coding: utf-8 -*-
"""
confirm_dialog - 次日工时确认弹窗
====================================

每个工作日打开电脑时弹出，显示前一天的上下班时间和工时，
用户可确认或修改下班时间。

版本: 0.4.2
"""

from datetime import datetime, date, timedelta

from PySide6 import QtWidgets, QtCore

from src.data import database
from src.config import SETTING_DAILY_REQUIRED_HOURS


class ConfirmYesterdayDialog(QtWidgets.QDialog):
    """
    次日工时确认弹窗。

    显示前一天的上/下班时间和工时，允许用户修改下班时间后确认。
    如果有异常记录，一并显示警告。
    """

    def __init__(self, work_date: date, parent=None):
        """
        初始化确认弹窗，加载指定日期的工时记录。

        Args:
            work_date: 要确认的工作日日期
            parent:    父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("昨日工时确认")
        self.setMinimumWidth(420)
        self.work_date = work_date

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(12)

        # ── 从 DB 读取记录 ──
        daily = database.get_daily_worktime(work_date)
        start_str = daily.get("start_time", "") if daily else ""
        end_str = daily.get("end_time", "") if daily else ""
        total = daily.get("total_hours", 0) if daily else 0
        # 优先从 DB 记录读 required_hours，fallback 到 settings
        rec_required = daily.get("required_hours") if daily else None
        required = rec_required if rec_required is not None else float(database.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))
        anomaly_note = daily.get("anomaly_note") if daily else None

        # ── 日期 ──
        layout.addWidget(QtWidgets.QLabel(f"日期：{work_date.isoformat()}"))

        # ── 上班时间 ──
        layout.addWidget(QtWidgets.QLabel(f"上班：{start_str[11:16] if len(start_str) > 11 else '无记录'}"))

        # ── 下班时间（可编辑）──
        layout.addWidget(QtWidgets.QLabel("下班时间："))
        self.end_time_edit = QtWidgets.QTimeEdit()
        if end_str and len(end_str) > 11:
            h, m = map(int, end_str[11:16].split(":"))
            self.end_time_edit.setTime(QtCore.QTime(h, m))
        else:
            self.end_time_edit.setTime(QtCore.QTime.currentTime())
        layout.addWidget(self.end_time_edit)

        # ── 工时 ──
        layout.addWidget(QtWidgets.QLabel(f"工时：{total:.2f} 小时 / 要求：{required:.1f} 小时"))

        # ── 异常警告（如有）──
        if anomaly_note:
            warn = QtWidgets.QLabel(f"⚠️ 检测到异常：{anomaly_note}")
            warn.setObjectName("AnomalyWarn")
            layout.addWidget(warn)

        # ── 确认/跳过按钮 ──
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("确认")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("跳过")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_end_time(self) -> datetime:
        """
        获取用户修改后的下班时间。

        Returns:
            下班时间 datetime（日期部分为 work_date）
        """
        t = self.end_time_edit.time()
        return datetime(self.work_date.year, self.work_date.month, self.work_date.day,
                         t.hour(), t.minute())
