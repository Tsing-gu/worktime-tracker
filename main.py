# -*- coding: utf-8 -*-
"""
main - 程序入口
=================

工时计算器的主入口，仅负责:
    1. 创建 QApplication
    2. 应用主题样式
    3. 创建主窗口（内含 service.init() 完成数据库+节假日初始化）
    4. 监听 dock 图标点击

所有业务逻辑由 src/ 下的分层模块处理，此文件保持极简。

版本: 0.8.0
"""

import sys

from PySide6 import QtWidgets, QtCore

from src.ui.theme import get_theme, build_qss
from src.ui.main_window import MainWindow
from src.utils.version import get_version


class _DockReopenFilter(QtCore.QObject):
    """捕获应用激活事件（macOS 点击 dock 图标时触发），重新展开主窗口。"""

    def __init__(self, window):
        super().__init__()
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.ApplicationActivate:
            if not self._window.isVisible():
                self._window.show_normal()
        return super().eventFilter(obj, event)


def main():
    """程序入口函数。"""
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，转入托盘

    # 启用高 DPI 图标
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # 应用主题样式
    theme = get_theme()
    app.setStyleSheet(build_qss(theme))

    # 打印版本信息
    print(f"工时计算器 v{get_version()} 启动中...")

    # 创建并显示主窗口（service.init() 在 MainWindow 内部调用）
    window = MainWindow()
    window.show()

    # 监听 dock 图标点击：应用被激活且主窗口不可见时重新展开
    _dock_filter = _DockReopenFilter(window)
    app.installEventFilter(_dock_filter)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
