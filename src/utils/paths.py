# -*- coding: utf-8 -*-
"""
paths - 资源路径解析工具
========================

统一资源文件路径解析，兼容开发环境和 PyInstaller 打包环境。

版本: 0.8.0
"""

import os
import sys


def _get_project_root() -> str:
    """获取项目根目录（开发环境）或 Resources 目录（打包环境）。"""
    if getattr(sys, "frozen", False):
        _base = os.path.dirname(sys._MEIPASS)  # Contents
        _project_root = os.path.join(_base, "Resources")
        if not os.path.exists(os.path.join(_project_root, "VERSION")):
            _project_root = sys._MEIPASS
        return _project_root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，兼容开发环境和 PyInstaller 打包环境。

    Args:
        relative_path: 相对项目根目录的路径（如 'resources/app.icns'）

    Returns:
        资源文件的绝对路径
    """
    return os.path.join(_get_project_root(), relative_path)
