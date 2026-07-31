"""
main - 程序入口
=================

工时计算器的主入口，仅负责:
    1. 初始化日志系统
    2. 创建 QApplication
    3. 应用主题样式
    4. 创建主窗口（内含 service.init() 完成数据库+节假日初始化）
    5. 监听 dock 图标点击

所有业务逻辑由 src/ 下的分层模块处理，此文件保持极简。

版本: 0.16.0
"""

import sys

from PySide6 import QtCore, QtWidgets

from src.ui.views.main_window import MainWindowUI
from src.ui.theme import build_qss, get_theme
from src.utils.logging_setup import setup_logging
from src.utils.version import get_version


class _DockReopenFilter(QtCore.QObject):
    """捕获应用激活事件 + 系统主题切换事件。"""

    def __init__(self, window: MainWindowUI) -> None:
        super().__init__()
        self._window = window
        self._app = QtWidgets.QApplication.instance()
        self._theme_timer: QtCore.QTimer | None = None

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.ApplicationActivate:
            if not self._window.isVisible():
                self._window.show_normal()
        elif event.type() == QtCore.QEvent.PaletteChange:
            # 系统切换深色/浅色模式时重新应用 QSS（防抖避免频繁触发）
            if self._theme_timer:
                self._theme_timer.stop()
            self._theme_timer = QtCore.QTimer()
            self._theme_timer.setSingleShot(True)
            self._theme_timer.timeout.connect(self._reapply_theme)
            self._theme_timer.start(200)
        return super().eventFilter(obj, event)

    def _reapply_theme(self) -> None:
        from src.ui.theme import ThemeManagerUI, build_qss, get_theme

        self._app.setStyleSheet(build_qss(get_theme()))
        ThemeManagerUI.instance().emit_changed()


def main() -> None:
    """程序入口函数。"""
    # 初始化日志系统（在其他模块加载前完成，确保各模块能用 getLogger）
    logger = setup_logging()
    logger.info("工时计算器 v%s 启动中...", get_version())

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，转入托盘

    # 启用高 DPI 图标
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # 加载 Qt 内置中文翻译，使标准按钮(OK/Cancel/Yes/No等)显示中文
    _translators = []
    for qm in ("qtbase", "qt"):
        tr = QtCore.QTranslator()
        if tr.load(
            QtCore.QLocale("zh_CN"),
            qm,
            "_",
            QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.TranslationsPath),
        ):
            app.installTranslator(tr)
            _translators.append(tr)

    # 应用主题样式
    theme = get_theme()
    app.setStyleSheet(build_qss(theme))

    # 创建并显示主窗口（service.init() 在 MainWindow 内部调用）
    window = MainWindowUI()
    window.show()

    # 监听 dock 图标点击：应用被激活且主窗口不可见时重新展开
    _dock_filter = _DockReopenFilter(window)
    app.installEventFilter(_dock_filter)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
