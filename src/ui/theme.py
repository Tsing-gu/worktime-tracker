# -*- coding: utf-8 -*-
"""
theme - 深色/浅色主题与 QSS 样式表
=====================================

根据 macOS 当前外观模式（深色/浅色）自动选择配色，
构建完整 QSS 样式表供 QApplication 使用。

版本: 0.4.2
"""

from PySide6 import QtWidgets, QtGui, QtCore


class ThemeManager(QtCore.QObject):
    """主题管理器：全局信号通知主题切换，任何窗口 connect 即可自动刷新。"""

    theme_changed = QtCore.Signal()

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def emit_changed(self):
        self.theme_changed.emit()


_theme_manager = ThemeManager.instance()


def is_dark_mode() -> bool:
    """
    检测 macOS 当前是否为深色模式。

    通过 QPalette 窗口背景亮度判断（亮度 < 128 = 深色）。

    Returns:
        True=深色模式, False=浅色模式
    """
    palette = QtWidgets.QApplication.palette()
    bg = palette.color(QtGui.QPalette.Window)
    return bg.lightness() < 128


def get_theme() -> dict:
    """
    根据当前系统外观模式返回主题配色字典。

    Returns:
        包含 bg/card/stroke/primary/main/sec/green/red/blue 等颜色的 dict
    """
    dark = is_dark_mode()
    if dark:
        return {
            "bg": "#000000", "card": "#1C1C1E", "card_alt": "#2C2C2E",
            "stroke": "#38383A", "primary": "#0A84FF",
            "main": "#FFFFFF", "sec": "#98989D",
            "green": "#30D158", "red": "#FF453A", "blue": "#5E5CE6",
            "track": "#2C2C2E", "div": "#38383A",
            "btn_bg": "#0A84FF", "btn_text": "#FFFFFF", "btn_border": "transparent",
            "btn_hover": "#0066CC", "btn_pressed": "#0052A3",
            "input_bg": "#2C2C2E",
            # 日历状态色（柔和底色 + 饱和前景色）
            "cal_green_bg": "#1B3A2A", "cal_green_fg": "#30D158",
            "cal_red_bg": "#3A1B1B", "cal_red_fg": "#FF6961",
            "cal_blue_bg": "#221D3A", "cal_blue_fg": "#9B8AFB",
            "cal_holiday_bg": "#2C2C2E", "cal_holiday_fg": "#98989D",
            "cal_weekend_bg": "#1C1C1E", "cal_weekend_fg": "#6B6B70",
            "cal_workday_bg": "#2C2C2E", "cal_workday_fg": "#98989D",
            "cal_overtime_bg": "#1A2238", "cal_overtime_fg": "#5AB4FF",
        }
    return {
        "bg": "#F5F5F7", "card": "#FFFFFF", "card_alt": "#F0F0F2",
        "stroke": "#E5E5EA", "primary": "#007AFF",
        "main": "#1D1D1F", "sec": "#86868B",
        "green": "#34C759", "red": "#FF3B30", "blue": "#5856D6",
        "track": "#E5E5EA", "div": "#E5E5EA",
        "btn_bg": "#007AFF", "btn_text": "#FFFFFF", "btn_border": "transparent",
        "btn_hover": "#0066CC", "btn_pressed": "#0052A3",
        "input_bg": "#F5F5F7",
        # 日历状态色（柔和底色 + 饱和前景色）
        "cal_green_bg": "#E8F8EE", "cal_green_fg": "#1A8B3A",
        "cal_red_bg": "#FDECEA", "cal_red_fg": "#D32F2F",
        "cal_blue_bg": "#EFEDF8", "cal_blue_fg": "#5B4FCF",
        "cal_holiday_bg": "#F0F0F2", "cal_holiday_fg": "#86868B",
        "cal_weekend_bg": "#F5F5F7", "cal_weekend_fg": "#AEAEB2",
        "cal_workday_bg": "#FFFFFF", "cal_workday_fg": "#86868B",
        "cal_overtime_bg": "#E8F0FE", "cal_overtime_fg": "#0A6CD9",
    }


def build_qss(t: dict) -> str:
    """
    根据主题配色字典构建完整 QSS 样式表字符串。

    覆盖所有 UI 组件样式：
        - QMainWindow / QDialog 背景色
        - QLabel 各命名样式（DateLabel, WorkedValue, CardTitle 等）
        - QFrame 卡片/分割线样式
        - QProgressBar 进度条
        - QPushButton 主按钮/次按钮/普通按钮
        - QGroupBox / QTableWidget / QSpinBox / QCheckBox / QComboBox
        - QMenu 右键菜单 / QScrollBar 滚动条
        - QCalendarWidget 日历控件
        - QMessageBox / QInputDialog 消息框

    Args:
        t: 主题配色字典（来自 get_theme()）

    Returns:
        QSS 样式表字符串
    """
    return f"""
    QMainWindow, QDialog {{
        background-color: {t['bg']};
    }}
    QWidget {{
        color: {t['main']};
        font-family: "PingFang SC", "Noto Sans SC", "Helvetica Neue", sans-serif;
        font-size: 14px;
    }}
    QLabel {{
        color: {t['main']};
        background: transparent;
        border: none;
    }}
    QLabel#DateLabel {{
        font-size: 20px;
        font-weight: bold;
        color: {t['main']};
    }}
    QLabel#WorkedValue {{
        font-size: 28px;
        font-weight: bold;
        color: {t['primary']};
    }}
    QLabel#WorkedSub {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#SecText {{
        font-size: 14px;
        color: {t['sec']};
    }}
    QLabel#SmallSec {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#CardTitle {{
        font-size: 14px;
        font-weight: bold;
        color: {t['main']};
    }}
    QLabel#CardLine {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#AnomalyWarn {{
        color: {t['red']};
        font-size: 13px;
    }}
    QFrame#Card {{
        background-color: {t['card']};
        border: 1px solid {t['stroke']};
        border-radius: 12px;
    }}
    QFrame#CardAlt {{
        background-color: {t['card_alt']};
        border: 1px solid {t['stroke']};
        border-radius: 12px;
    }}
    QFrame#Divider {{
        background-color: {t['div']};
        border: none;
        max-height: 1px;
    }}
    QProgressBar {{
        background-color: {t['track']};
        border: none;
        border-radius: 4px;
        text-align: center;
        font-size: 11px;
        color: {t['sec']};
        min-height: 8px;
        max-height: 8px;
    }}
    QProgressBar::chunk {{
        background-color: {t['primary']};
        border-radius: 4px;
    }}
    QProgressBar#CardBar {{
        min-height: 6px;
        max-height: 6px;
        border-radius: 3px;
        text-align: center;
    }}
    QProgressBar#CardBar::chunk {{
        background-color: {t['primary']};
        border-radius: 3px;
    }}
    QPushButton {{
        background-color: {t['card']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
        border-radius: 8px;
        padding: 6px 16px;
        font-size: 13px;
        font-weight: 500;
        min-height: 24px;
        outline: none;
    }}
    QPushButton:hover {{
        background-color: {t['card_alt']};
        border-color: {t['primary']};
    }}
    QPushButton:focus {{
        background-color: {t['card_alt']};
        border-color: {t['primary']};
        outline: none;
    }}
    QPushButton:pressed {{
        background-color: {t['stroke']};
    }}
    QPushButton#PrimaryBtn {{
        background-color: {t['btn_bg']};
        color: {t['btn_text']};
        border: none;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        padding: 6px 12px;
        min-height: 20px;
    }}
    QPushButton#PrimaryBtn:hover {{
        background-color: {t['btn_hover']};
    }}
    QPushButton#PrimaryBtn:pressed {{
        background-color: {t['btn_pressed']};
    }}
    QPushButton#SecondaryBtn {{
        background-color: {t['card']};
        color: {t['primary']};
        border: 1px solid {t['primary']};
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        padding: 6px 12px;
        min-height: 20px;
    }}
    QPushButton#SecondaryBtn:hover {{
        background-color: {t['card_alt']};
    }}
    QPushButton#SecondaryBtn:pressed {{
        background-color: {t['stroke']};
    }}
    QGroupBox {{
        background-color: {t['card']};
        border: 1px solid {t['stroke']};
        border-radius: 12px;
        margin-top: 8px;
        padding: 16px;
        font-weight: bold;
        font-size: 14px;
        color: {t['main']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 4px;
        color: {t['main']};
    }}
    QTableWidget {{
        background-color: {t['card']};
        border: 1px solid {t['stroke']};
        border-radius: 8px;
        gridline-color: {t['stroke']};
        color: {t['main']};
    }}
    QTableWidget::item {{
        padding: 6px;
        border: none;
    }}
    QHeaderView::section {{
        background-color: {t['card_alt']};
        color: {t['main']};
        font-weight: bold;
        padding: 8px;
        border: none;
        border-bottom: 1px solid {t['stroke']};
    }}
    QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit, QLineEdit {{
        background-color: {t['input_bg']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 14px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus, QTimeEdit:focus, QDateEdit:focus, QLineEdit:focus {{
        border-color: {t['primary']};
    }}
    QCheckBox {{
        color: {t['main']};
        font-size: 14px;
        spacing: 8px;
    }}
    QComboBox {{
        background-color: {t['input_bg']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 14px;
    }}
    QComboBox:focus {{
        border-color: {t['primary']};
    }}
    QComboBox QAbstractItemView {{
        background-color: {t['card']};
        color: {t['main']};
        selection-background-color: {t['primary']};
        border: 1px solid {t['stroke']};
        border-radius: 6px;
        padding: 4px;
    }}
    QDialogButtonBox QPushButton {{
        min-width: 72px;
        border: 1px solid {t['stroke']};
        border-radius: 8px;
        padding: 6px 16px;
        font-size: 13px;
        font-weight: 500;
        min-height: 24px;
        background-color: {t['card']};
        color: {t['main']};
    }}
    QDialogButtonBox QPushButton:hover {{
        background-color: {t['card_alt']};
        border-color: {t['primary']};
    }}
    QDialogButtonBox QPushButton:focus {{
        background-color: {t['card_alt']};
        border-color: {t['primary']};
        outline: none;
    }}
    QDialogButtonBox QPushButton:pressed {{
        background-color: {t['stroke']};
    }}
    QMenu {{
        background-color: {t['card']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {t['primary']};
        color: white;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t['stroke']};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t['sec']};
    }}
    QCalendarWidget {{
        background-color: {t['card']};
        border: 1px solid {t['stroke']};
        border-radius: 12px;
    }}
    QCalendarWidget QToolButton {{
        color: {t['main']};
        background: transparent;
        border: none;
        padding: 4px 8px;
        font-size: 14px;
        font-weight: bold;
        min-height: 28px;
    }}
    QCalendarWidget QToolButton:hover {{
        color: {t['primary']};
    }}
    QCalendarWidget QMenu {{
        background-color: {t['card']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
    }}
    QCalendarWidget QSpinBox {{
        background-color: {t['input_bg']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
        border-radius: 4px;
        padding: 2px 4px;
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: {t['bg']};
        color: {t['main']};
        selection-background-color: {t['primary']};
        selection-color: white;
        border: none;
        font-size: 13px;
    }}
    QCalendarWidget QAbstractItemView:enabled {{
        color: {t['main']};
        font-size: 12px;
    }}
    #qt_calendar_navigationbar {{
        background-color: {t['card_alt']};
        border-bottom: 1px solid {t['stroke']};
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
    }}
    #qt_calendar_calendarview {{
        border: none;
        background: {t['card']};
    }}
    QFrame#DayCell {{
        background-color: {t['card']};
        border: 1px solid {t['stroke']};
        border-radius: 8px;
    }}
    QFrame#DayCell:hover {{
        border-color: {t['primary']};
    }}
    QFrame#DayCell QLabel {{
        font-size: 14px;
    }}
    QLabel#DayCellInfo {{
        font-size: 9px;
    }}
    QLabel#WeekHeader {{
        font-size: 13px;
        font-weight: bold;
        color: {t['sec']};
        background-color: {t['card_alt']};
        border-radius: 6px;
    }}
    QLabel#TrayWorked {{
        font-size: 16px;
        font-weight: bold;
        color: {t['primary']};
    }}
    QLabel#TrayPct {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#TrayOff {{
        font-size: 14px;
        color: {t['green']};
    }}
    QLabel#TrayETA {{
        font-size: 13px;
        color: {t['sec']};
    }}
    QLabel#TrayReached {{
        font-size: 14px;
        color: {t['green']};
        font-weight: bold;
    }}
    QLabel#TrayRemaining {{
        font-size: 14px;
        color: {t['main']};
    }}
    QLabel#UpdateTitle {{
        font-size: 18px;
        font-weight: bold;
        color: {t['primary']};
    }}
    QLabel#UpdateCur {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#UpdateDesc {{
        font-size: 13px;
        color: {t['main']};
    }}
    QLabel#DlStatus {{
        font-size: 14px;
        color: {t['main']};
    }}
    QLabel#DlDetail {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#VersionLabel {{
        font-size: 12px;
        color: {t['sec']};
    }}
    QLabel#OfficeDomain {{
        color: {t['sec']};
    }}
    QPushButton#DangerBtn {{
        background-color: {t['card']};
        color: {t['red']};
        border: 1px solid {t['red']};
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        padding: 6px 12px;
        min-height: 20px;
    }}
    QPushButton#DangerBtn:hover {{
        background-color: {t['card_alt']};
    }}
    QPushButton#DangerBtn:pressed {{
        background-color: {t['stroke']};
    }}
    QToolTip {{
        background-color: {t['card']};
        color: {t['main']};
        border: 1px solid {t['stroke']};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QMessageBox, QInputDialog {{
        background-color: {t['bg']};
    }}
    QMessageBox QLabel, QInputDialog QLabel {{
        color: {t['main']};
        font-size: 14px;
    }}
    """
