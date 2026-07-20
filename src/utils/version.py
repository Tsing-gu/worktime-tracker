# -*- coding: utf-8 -*-
"""
version - 版本管理 + CHANGELOG 自动更新
========================================

提供版本号读取和变更记录功能。

版本号格式: 0.MINOR.PATCH（正式版前 MAJOR 固定为 0）

使用方式:
    from src.utils.version import record_change
    record_change("added", "新增手动补录功能")   # 自动 bump PATCH 版本并写入 CHANGELOG

变更类型:
    - added:   新增功能 → bump PATCH
    - changed: 功能改变 → bump MINOR
    - fixed:   修复缺陷 → bump PATCH
    - removed: 移除功能 → bump MINOR（正式版前不 bump MAJOR）

版本号文件: 项目根目录 VERSION
变更记录文件: 项目根目录 CHANGELOG.md

版本: 0.4.2
"""

import os
import sys
from datetime import date

# 项目根目录（src/utils/ 往上两级）
# 打包后从 _MEIPASS 读 VERSION/CHANGELOG，开发环境从项目根目录读
if getattr(sys, "frozen", False):
    # PyInstaller .app 模式下 _MEIPASS = Contents/MacOS，VERSION 放在 Resources
    _base = os.path.dirname(sys._MEIPASS)  # Contents
    _PROJECT_ROOT = os.path.join(_base, "Resources")
    if not os.path.exists(os.path.join(_PROJECT_ROOT, "VERSION")):
        _PROJECT_ROOT = sys._MEIPASS
else:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_VERSION_FILE = os.path.join(_PROJECT_ROOT, "VERSION")
_CHANGELOG_FILE = os.path.join(_PROJECT_ROOT, "CHANGELOG.md")

# 变更类型 → 版本 bump 级别
# 正式版前 MAJOR 固定为 0，removed 改为 bump MINOR
# minor: 次位 +1, patch: 末位 +1
_BUMP_MAP = {
    "removed": "minor",
    "changed": "minor",
    "added": "patch",
    "fixed": "patch",
}

# 变更类型的中文显示名
_TYPE_LABEL = {
    "added": "新增",
    "changed": "变更",
    "fixed": "修复",
    "removed": "移除",
}


def get_version() -> str:
    """
    读取当前版本号。

    Returns:
        版本号字符串（如 "0.4.0"），文件不存在时返回 "0.0.0"
    """
    if not os.path.exists(_VERSION_FILE):
        return "0.0.0"
    with open(_VERSION_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def _bump_version(current: str, level: str) -> str:
    """
    根据变更级别递增版本号。

    版本格式: 0.MINOR.PATCH（MAJOR 固定为 0）

    Args:
        current: 当前版本号 "0.MINOR.PATCH"
        level:   bump 级别 "minor" | "patch"

    Returns:
        新版本号字符串
    """
    parts = [int(x) for x in current.split(".")]
    # 补齐到三位
    while len(parts) < 3:
        parts.append(0)

    if level == "major":
        # 正式版前不 bump MAJOR，转为 bump MINOR
        parts[1] += 1
        parts[2] = 0
    elif level == "minor":
        parts[1] += 1
        parts[2] = 0
    elif level == "patch":
        parts[2] += 1

    return ".".join(str(p) for p in parts[:3])


def record_change(change_type: str, description: str) -> str:
    """
    记录一条变更并自动 bump 版本号。

    步骤:
        1. 根据变更类型决定 bump 级别
        2. 更新 VERSION 文件
        3. 在 CHANGELOG.md 顶部追加变更条目

    注意：此函数仅用于开发环境，打包后调用会抛异常。
    """
    if getattr(sys, "frozen", False):
        raise RuntimeError("record_change 不可在打包环境调用")

    if change_type not in _BUMP_MAP:
        raise ValueError(f"无效的变更类型: {change_type}，应为 {list(_BUMP_MAP.keys())}")

    current = get_version()
    level = _BUMP_MAP[change_type]
    new_version = _bump_version(current, level)

    # 更新 VERSION 文件
    with open(_VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(new_version)

    # 追加 CHANGELOG 条目
    today_str = date.today().isoformat()
    label = _TYPE_LABEL.get(change_type, change_type)
    entry = f"## [{new_version}] - {today_str}\n\n- **{label}**: {description}\n\n"

    # 读取已有内容并拼接（新条目置顶）
    existing = ""
    if os.path.exists(_CHANGELOG_FILE):
        with open(_CHANGELOG_FILE, "r", encoding="utf-8") as f:
            existing = f.read()

    with open(_CHANGELOG_FILE, "w", encoding="utf-8") as f:
        f.write(entry + existing)

    return new_version
