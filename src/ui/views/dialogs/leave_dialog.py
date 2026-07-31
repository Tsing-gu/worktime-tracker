"""
leave_dialog - 请假弹窗
==========================

提供请假日期和请假类型的选择界面。

版本: 0.4.2
"""

from datetime import date

from PySide6 import QtCore, QtWidgets

from src.config import LEAVE_TYPES
from src.ui.components.dialog_buttons import make_dialog_button
from src.ui.theme.metrics import DIALOG_BOTTOM_MARGIN, DIALOG_MARGIN, MEDIUM_DIALOG_WIDTH


class LeaveDialogUI(QtWidgets.QDialog):
    """
    请假弹窗对话框。

    用户选择请假日期和请假类型（年假/病假/事假/调休），
    确认后通过 get_date() 和 get_leave_type() 返回结果。
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None, default_date: date | None = None):
        """
        初始化请假弹窗。

        Args:
            parent:       父窗口
            default_date: 默认请假日期（默认今天）
        """
        super().__init__(parent)
        self.setWindowTitle("请假")
        self.setMinimumWidth(MEDIUM_DIALOG_WIDTH)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_BOTTOM_MARGIN)
        layout.setSpacing(12)

        # ── 请假日期选择 ──
        layout.addWidget(QtWidgets.QLabel("请假日期："))
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        if default_date:
            self.date_edit.setDate(
                QtCore.QDate(default_date.year, default_date.month, default_date.day)
            )
        else:
            self.date_edit.setDate(QtCore.QDate.currentDate())
        layout.addWidget(self.date_edit)

        # ── 请假类型选择 ──
        layout.addWidget(QtWidgets.QLabel("请假类型："))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.type_map = LEAVE_TYPES  # {"annual": "年假", "sick": "病假", ...}
        for t in self.type_map:
            self.type_combo.addItem(self.type_map[t])
        layout.addWidget(self.type_combo)

        # ── 确认/取消按钮（手动创建两个实例，避免 QDialogButtonBox 焦点链问题）──
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = make_dialog_button("取消", "secondary", self.reject)
        ok_btn = make_dialog_button("确认请假", "primary", self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def get_date(self) -> date:
        """
        获取用户选择的请假日期。

        Returns:
            请假日期 date 对象
        """
        qd = self.date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def get_leave_type(self) -> str:
        """
        获取用户选择的请假类型代号。

        Returns:
            请假类型代号 (annual/sick/personal/compensatory)
        """
        return self.type_map[self.type_combo.currentText()]
