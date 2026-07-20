# -*- coding: utf-8 -*-
"""
theme - 深色/浅色主题与 QSS 样式表
=====================================

根据 macOS 当前外观模式（深色/浅色）自动选择配色，
构建完整 QSS 样式表供 QApplication 使用。

版本: 0.4.2
"""

from PySide6 import QtWidgets, QtGui


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
            "bg": "#1C1C1E", "card": "#2C2C2E", "card_alt": "#3A3A3C",
            "stroke": "#3A3A3C", "primary": "#0A84FF",
            "main": "#FFFFFF", "sec": "#98989D",
            "green": "#30D158", "red": "#FF453A", "blue": "#64D2FF",
            "track": "#4A4A4C", "div": "#3A3A3C",
            "btn_bg": "#0A84FF", "btn_text": "#FFFFFF", "btn_border": "transparent",
            "input_bg": "#3A3A3C",
        }
    return {
        "bg": "#F5F5F7", "card": "#FFFFFF", "card_alt": "#F0F0F2",
        "stroke": "#E5E5EA", "primary": "#0A84FF",
        "main": "#1D1D1F", "sec": "#86868B",
        "green": "#30D158", "red": "#FF453A", "blue": "#64D2FF",
        "track": "#E5E5EA", "div": "#E5E5EA",
        "btn_bg": "#0A84FF", "btn_text": "#FFFFFF", "btn_border": "transparent",
        "input_bg": "#F5F5F7",
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
    }}
    QPushButton:hover {{
        background-color: {t['card_alt']};
        border-color: {t['primary']};
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
        background-color: #0066CC;
    }}
    QPushButton#PrimaryBtn:pressed {{
        background-color: #0052A3;
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
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid {t['stroke']};
        background: {t['input_bg']};
    }}
    QCheckBox::indicator:checked {{
        background: {t['primary']};
        border-color: {t['primary']};
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
    QMessageBox, QInputDialog {{
        background-color: {t['bg']};
    }}
    QMessageBox QLabel, QInputDialog QLabel {{
        color: {t['main']};
        font-size: 14px;
    }}
    """
