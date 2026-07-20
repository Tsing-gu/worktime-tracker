# -*- coding: utf-8 -*-
"""
main - 程序入口
=================

工时计算器的主入口，仅负责:
    1. 创建 QApplication
    2. 应用主题样式
    3. 初始化数据库 + 节假日
    4. 创建并显示主窗口

所有业务逻辑由 src/ 下的分层模块处理，此文件保持极简。

版本: 0.5.2
"""

import sys
from datetime import date

from PySide6 import QtWidgets, QtCore

from src.data import database
from src.core import holiday
from src.ui.theme import get_theme, build_qss
from src.ui.main_window import MainWindow
from src.utils.version import get_version


def main():
    """
    程序入口函数。

    执行步骤:
        1. 创建 QApplication（关闭"最后一个窗口关闭即退出"行为，支持托盘驻留）
        2. 检测系统深色/浅色模式并应用对应 QSS 主题
        3. 初始化 SQLite 数据库
        4. 加载本年度节假日数据
        5. 创建主窗口并显示

    窗口关闭后转入菜单栏托盘继续运行，只有用户从托盘菜单选择"退出"才会终止程序。
    """
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，转入托盘

    # 启用高 DPI 图标
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # 应用主题样式
    theme = get_theme()
    app.setStyleSheet(build_qss(theme))

    # 初始化数据层
    database.init_db()
    holiday.ensure_holidays_loaded(date.today().year)

    # 打印版本信息
    print(f"工时计算器 v{get_version()} 启动中...")

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
