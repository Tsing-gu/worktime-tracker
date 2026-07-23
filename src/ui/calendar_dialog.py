# -*- coding: utf-8 -*-
"""
calendar_dialog - 日历历史弹窗
================================

以日历网格视图展示每月的工时记录，支持右键操作。

功能:
    - 日历网格: 每天一格，显示工时和达标状态（绿色达标/红色不足/蓝色请假/灰色节假日）
    - 右键菜单: 请假 / 手动补录 / 清除记录
    - 导出:     导出当月 CSV / Excel
    - 月份切换: 前/后月 + 回到本月

版本: 0.4.2
"""

from datetime import datetime, date, timedelta

from PySide6 import QtWidgets, QtCore, QtGui

from src.config import SETTING_DAILY_REQUIRED_HOURS, LEAVE_TYPES
from src.services.worktime_service import WorktimeService
from src.core.date_utils import compute_work_date
from src.ui.leave_dialog import LeaveDialog
from src.ui.theme import get_theme


class DayCell(QtWidgets.QFrame):
    """
    日历中单个日期格。

    显示日期数字和工时/状态信息，支持右键菜单。

    Attributes:
        work_date: 该格对应的日期
    """

    def __init__(self, day: int, work_date: date, parent=None):
        """
        初始化日期格。

        Args:
            day:       日期数字（1-31）
            work_date: 完整日期
            parent:    父控件
        """
        super().__init__(parent)
        self.work_date = work_date
        self.setObjectName("DayCell")
        self.setFixedSize(88, 76)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        # 日期数字
        self.day_label = QtWidgets.QLabel(str(day))
        self.day_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.day_label.setAlignment(QtCore.Qt.AlignLeft)
        layout.addWidget(self.day_label)

        # 工时/状态信息
        self.info_label = QtWidgets.QLabel("")
        self.info_label.setStyleSheet("font-size: 11px;")
        self.info_label.setAlignment(QtCore.Qt.AlignLeft)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        layout.addStretch()

        # 启用右键菜单
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

    def set_status(self, text: str, bg_color: str, fg_color: str = ""):
        """
        设置日期格的显示文本和背景色。

        Args:
            text:     显示文本（工时/状态）
            bg_color: 背景色（CSS 颜色值）
            fg_color: 前景色（可选，默认不改变）
        """
        self.info_label.setText(text)
        style = f"QFrame#DayCell {{ background-color: {bg_color}; border-radius: 8px; border: 1px solid transparent; }}"
        if fg_color:
            style += f" QLabel {{ color: {fg_color}; }}"
        self.setStyleSheet(style)


class CalendarHistoryDialog(QtWidgets.QDialog):
    """
    日历历史弹窗。

    以月历形式展示工时记录，支持右键请假/补录/清除，
    以及当月数据导出。
    """

    def __init__(self, parent=None, service: WorktimeService = None):
        """
        初始化日历弹窗。

        Args:
            parent:  父窗口
            service: WorktimeService 实例（用于数据操作）
        """
        super().__init__(parent)
        self.setWindowTitle("日历")
        self.setMinimumSize(720, 600)
        self.service = service or WorktimeService()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ── 顶部控制栏 ──
        ctrl = QtWidgets.QHBoxLayout()
        ctrl.setSpacing(8)

        prev_btn = QtWidgets.QPushButton("<")
        prev_btn.setFixedSize(36, 30)
        prev_btn.clicked.connect(self.prev_month)
        ctrl.addWidget(prev_btn)

        self.month_label = QtWidgets.QLabel("")
        self.month_label.setObjectName("DateLabel")
        self.month_label.setAlignment(QtCore.Qt.AlignCenter)
        ctrl.addWidget(self.month_label)
        ctrl.addStretch()

        next_btn = QtWidgets.QPushButton(">")
        next_btn.setFixedSize(36, 30)
        next_btn.clicked.connect(self.next_month)
        ctrl.addWidget(next_btn)

        today_btn = QtWidgets.QPushButton("本月")
        today_btn.clicked.connect(self.go_today)
        ctrl.addWidget(today_btn)
        ctrl.addSpacing(16)

        export_csv_btn = QtWidgets.QPushButton("导出CSV")
        export_csv_btn.clicked.connect(lambda: self.export_data("csv"))
        ctrl.addWidget(export_csv_btn)

        export_xlsx_btn = QtWidgets.QPushButton("导出Excel")
        export_xlsx_btn.clicked.connect(lambda: self.export_data("excel"))
        ctrl.addWidget(export_xlsx_btn)
        layout.addLayout(ctrl)

        # ── 星期表头 ──
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(4)
        for name in ["一", "二", "三", "四", "五", "六", "日"]:
            lbl = QtWidgets.QLabel(name)
            lbl.setObjectName("SmallSec")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setFixedSize(88, 24)
            header_row.addWidget(lbl)
        layout.addLayout(header_row)

        # ── 日历网格容器 ──
        self.grid_container = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(4)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.grid_container)
        layout.addStretch()

        # ── 底部说明 ──
        info_label = QtWidgets.QLabel("右键日期可请假/补录/清除 | 绿色=达标 红色=不足 蓝色=请假 灰色=节假日")
        info_label.setObjectName("SmallSec")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(info_label)

        # 当前显示的年/月
        _today = compute_work_date(datetime.now())
        self._current_year = _today.year
        self._current_month = _today.month
        self._cells = []

        self.load_data()

    # ─── 月份切换 ──────────────────────────────────────────

    def prev_month(self):
        """切换到上一个月。"""
        if self._current_month == 1:
            self._current_month = 12
            self._current_year -= 1
        else:
            self._current_month -= 1
        self.load_data()

    def next_month(self):
        """切换到下一个月。"""
        if self._current_month == 12:
            self._current_month = 1
            self._current_year += 1
        else:
            self._current_month += 1
        self.load_data()

    def go_today(self):
        """跳回本月。"""
        _today = compute_work_date(datetime.now())
        self._current_year = _today.year
        self._current_month = _today.month
        self.load_data()

    # ─── 数据加载 ──────────────────────────────────────────

    def load_data(self):
        """
        加载当前月份的工时记录并渲染日历网格。

        遍历当月每一天，根据 DB 记录和节假日数据设置日期格的显示状态:
            - 请假 → 蓝色
            - 法定假日 → 灰色
            - 调休上班日 → 蓝色浅底
            - 有工时记录 → 绿色(达标)/红色(不足)
            - 无记录工作日 → 默认
            - 周末 → 灰色
        """
        year, month = self._current_year, self._current_month
        self.month_label.setText(f"{year}年{month}月")

        # 清空旧网格
        for i in reversed(range(self.grid_layout.count())):
            w = self.grid_layout.itemAt(i).widget()
            if w:
                self.grid_layout.removeWidget(w)
                w.deleteLater()
        self._cells = []

        # 计算月份范围
        start = date(year, month, 1)
        if month == 12:
            end = date(year, month, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)

        # 从 service 获取数据
        records = self.service.get_date_range_worktime(start, end)
        holidays = self.service.get_all_holidays()
        records_map = {r["work_date"]: r for r in records}
        holidays_map = {h["date"]: h for h in holidays}

        theme = get_theme()
        default_required = float(self.service.get_setting(SETTING_DAILY_REQUIRED_HOURS, "8.0"))

        # 计算起始位置（周一起始）
        first_weekday = start.weekday()
        d = start
        row = 0
        col = first_weekday

        while d <= end:
            key = d.isoformat()
            rec = records_map.get(key)
            hol = holidays_map.get(key)

            cell = DayCell(d.day, d, self.grid_container)
            cell.customContextMenuRequested.connect(lambda pos, c=cell: self.on_right_click(c))

            # ── 状态判定优先级 ──
            if rec and rec.get("leave_type") and rec["leave_type"] != "none":
                # 请假
                leave_text = LEAVE_TYPES.get(rec["leave_type"], rec["leave_type"])
                cell.set_status(leave_text, f"{theme['blue']}30", theme["blue"])
            elif hol and hol.get("is_off_day"):
                # 法定假日
                cell.set_status(hol["name"], theme["card_alt"], theme["sec"])
            elif hol and not hol.get("is_off_day"):
                # 调休上班日
                total = rec.get("total_hours", 0) if rec else 0
                cell.set_status(f"调休 {total:.1f}h" if total else "调休上班", f"{theme['primary']}20", theme["primary"])
            elif rec and rec.get("total_hours"):
                # 有工时记录
                total = rec["total_hours"]
                # 逐条从 DB 读 required_hours，fallback 到默认值
                rec_required = rec.get("required_hours")
                cell_required = rec_required if rec_required is not None else default_required
                reached = total >= cell_required
                start_str = rec.get("start_time") or ""
                end_str = rec.get("end_time") or ""
                start_short = start_str[11:16] if len(start_str) > 11 else ""
                end_short = end_str[11:16] if len(end_str) > 11 else ""
                if reached:
                    cell.set_status(f"{total:.1f}h\n{start_short}-{end_short}", f"{theme['green']}30", theme["green"])
                else:
                    cell.set_status(f"{total:.1f}h\n{start_short}-{end_short}", f"{theme['red']}30", theme["red"])
            else:
                # 无记录
                if d.weekday() >= 5:
                    cell.set_status("周末", theme["card_alt"], theme["sec"])
                else:
                    cell.set_status("--", theme["card"], theme["sec"])

            # 标记今天（按 6:00 跨天归属）
            if d == compute_work_date(datetime.now()):
                cell.setStyleSheet(cell.styleSheet() + f"QFrame#DayCell {{ border: 2px solid {theme['primary']}; }}")

            self.grid_layout.addWidget(cell, row, col)
            self._cells.append(cell)

            col += 1
            if col >= 7:
                col = 0
                row += 1
            d += timedelta(days=1)

    # ─── 右键菜单 ──────────────────────────────────────────

    def on_right_click(self, cell: DayCell):
        """
        处理日期格右键菜单。

        提供三个操作: 请假 / 手动补录或编辑 / 清除记录

        Args:
            cell: 被右键点击的日期格
        """
        wd = cell.work_date
        work_date_str = wd.isoformat()
        menu = QtWidgets.QMenu(self)
        act_leave = menu.addAction("请假")
        act_edit = menu.addAction("手动补录/编辑")
        act_clear = menu.addAction("清除记录")
        action = menu.exec_(cell.mapToGlobal(QtCore.QPoint(10, 10)))

        if action == act_leave:
            self.mark_leave(work_date_str)
        elif action == act_edit:
            self.manual_edit(work_date_str)
        elif action == act_clear:
            self.clear_record(work_date_str)

    def mark_leave(self, work_date_str: str):
        """
        打开请假弹窗并保存请假记录。

        Args:
            work_date_str: 工作日日期字符串
        """
        wd = date.fromisoformat(work_date_str)
        dialog = LeaveDialog(self, default_date=wd)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            leave_date = dialog.get_date()
            leave_type = dialog.get_leave_type()
            self.service.mark_leave(leave_date, leave_type)
            self.load_data()

    def manual_edit(self, work_date_str: str):
        """
        手动补录/编辑某天的上下班时间。

        通过两次 QInputDialog 输入上班和下班时间。

        Args:
            work_date_str: 工作日日期字符串
        """
        wd = date.fromisoformat(work_date_str)
        existing = self.service.get_daily_worktime(wd)
        start_default = ""
        end_default = ""
        if existing:
            if existing.get("start_time"):
                start_default = existing["start_time"][11:16]
            if existing.get("end_time"):
                end_default = existing["end_time"][11:16]

        # 输入上班时间
        start_str = self._input_dialog(f"{work_date_str} 上班时间 (HH:MM)：", start_default)
        if start_str is None:
            return
        # 输入下班时间
        end_str = self._input_dialog(f"{work_date_str} 下班时间 (HH:MM)：", end_default)
        if end_str is None:
            return

        # 调用 service 保存
        try:
            self.service.manual_record(wd, start_str, end_str)
            self.load_data()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "格式错误", str(e))

    def _input_dialog(self, label_text: str, default_text: str = ""):
        """自定义文本输入对话框（按钮中文化）。返回文本或 None（取消）。"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("手动补录")
        dialog.setMinimumWidth(280)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel(label_text))
        edit = QtWidgets.QLineEdit(default_text)
        edit.setPlaceholderText("HH:MM")
        layout.addWidget(edit)
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("确定")
        btn_box.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            return edit.text().strip()
        return None

    def clear_record(self, work_date_str: str):
        """
        清除指定日期的工时记录（需二次确认）。

        Args:
            work_date_str: 工作日日期字符串
        """
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("确认")
        msg.setText(f"确认清除 {work_date_str} 的记录？")
        yes_btn = msg.addButton("确认", QtWidgets.QMessageBox.YesRole)
        msg.addButton("取消", QtWidgets.QMessageBox.NoRole)
        msg.exec()
        if msg.clickedButton() == yes_btn:
            self.service.clear_record(work_date_str)
            self.load_data()

    # ─── 导出 ─────────────────────────────────────────────

    def export_data(self, fmt: str):
        """
        导出当前查看月份的数据。

        Args:
            fmt: 导出格式 "csv" 或 "excel"
        """
        year, month = self._current_year, self._current_month
        if month == 12:
            start = date(year, month, 1)
            end = date(year, month, 31)
        else:
            start = date(year, month, 1)
            end = date(year, month + 1, 1) - timedelta(days=1)

        exporter = self.service.get_exporter()
        if fmt == "csv":
            path = exporter.to_csv(start, end)
        else:
            path = exporter.to_excel(start, end)

        QtWidgets.QMessageBox.information(self, "导出成功", f"文件已保存到：\n{path}")
