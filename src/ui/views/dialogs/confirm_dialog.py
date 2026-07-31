"""
confirm_dialog - 次日工时确认弹窗
====================================

每个工作日打开电脑时弹出，显示前一天的上下班时间和工时，
用户可确认或修改下班时间。

版本: 0.8.0
"""

from datetime import date, datetime

from PySide6 import QtCore, QtWidgets

from src.ui.components.dialog_buttons import make_dialog_button
from src.ui.theme.metrics import DIALOG_BOTTOM_MARGIN, DIALOG_MARGIN, MEDIUM_DIALOG_WIDTH


class ConfirmYesterdayDialogUI(QtWidgets.QDialog):
    """
    次日工时确认弹窗。

    显示前一天的上/下班时间和工时，允许用户修改下班时间后确认。
    如果有异常记录，一并显示警告。
    """

    def __init__(
        self,
        work_date: date,
        daily: dict,
        required: float,
        parent: QtWidgets.QWidget | None = None,
    ):
        """
        初始化确认弹窗，从传入的记录数据填充界面。

        Args:
            work_date: 要确认的工作日日期
            daily:     该日的工时记录 dict（可为 None）
            required:  每日工时要求（小时）
            parent:    父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("昨日工时确认")
        self.setMinimumWidth(MEDIUM_DIALOG_WIDTH)
        self.work_date = work_date

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_BOTTOM_MARGIN)
        layout.setSpacing(12)

        # ── 从传入的记录读取 ──
        start_str = daily.get("start_time", "") if daily else ""
        end_str = daily.get("end_time", "") if daily else ""
        total = daily.get("total_hours", 0) if daily else 0
        anomaly_note = daily.get("anomaly_note") if daily else None

        # ── 日期 ──
        layout.addWidget(QtWidgets.QLabel(f"日期：{work_date.isoformat()}"))

        # ── 上班时间 ──
        layout.addWidget(
            QtWidgets.QLabel(f"上班：{start_str[11:16] if len(start_str) > 11 else '无记录'}")
        )

        # ── 下班时间（可编辑）──
        layout.addWidget(QtWidgets.QLabel("下班时间："))
        self.end_time_edit = QtWidgets.QTimeEdit()
        self.end_time_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
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

        # ── 确认/跳过按钮（手动创建两个实例，避免 QDialogButtonBox 焦点链问题）──
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        skip_btn = make_dialog_button("跳过", "secondary", self.reject)
        ok_btn = make_dialog_button("确认", "primary", self.accept)
        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def get_end_time(self) -> datetime:
        """获取用户修改后的下班时间。"""
        t = self.end_time_edit.time()
        return datetime(
            self.work_date.year, self.work_date.month, self.work_date.day, t.hour(), t.minute()
        )
