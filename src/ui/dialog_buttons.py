"""
dialog_buttons - 对话框按钮封装
================================

统一创建 QPushButton，避免 macOS 上的「首次点击被吞」问题。

核心问题:
    macOS 的 QPushButton 默认 autoDefault=True，首次点击只用来获取焦点，
    不触发 clicked 信号。QDialogButtonBox 更糟——点击非默认按钮后会把焦点
    切到默认按钮（TabFocusReason），即使 setAutoDefault(False) 也关不掉。

解法:
    所有按钮统一配置:
    - setAutoDefault(False) + setDefault(False): 彻底关闭默认按钮行为
    - setFocusPolicy(StrongFocus): 可接收焦点，对话框 show() 后 Qt 自动给首个按钮焦点
    - setObjectName: PrimaryBtn / SecondaryBtn / DangerBtn（QSS 主题样式）

API:
    make_dialog_button(text, role, slot) -> QPushButton

版本: 0.16.3
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtWidgets

# 按钮角色 → QSS objectName 映射
_ROLE_TO_OBJECT_NAME = {
    "primary": "PrimaryBtn",
    "secondary": "SecondaryBtn",
    "danger": "DangerBtn",
}


def make_dialog_button(
    text: str,
    role: str,
    slot: Callable[[], None],
    *,
    fixed_height: int = 32,
    fixed_size: tuple[int, int] | None = None,
) -> QtWidgets.QPushButton:
    """创建对话框按钮（统一配置，避免 macOS 焦点链问题）。

    Args:
        text:        按钮文字
        role:        "primary"（确定类）/ "secondary"（取消类）/ "danger"（危险操作）
        slot:        点击回调
        fixed_height: 固定高度（默认 32）
        fixed_size:  (width, height) 固定尺寸（优先于 fixed_height）

    Returns:
        配置好的 QPushButton 实例

    Note:
        一个按钮一个实例，调用方自行布局。不要封装「按钮对」返回布局，
        那会让两个按钮共享一个布局对象，违反「一个控件一个实例」原则。
    """
    btn = QtWidgets.QPushButton(text)
    btn.setObjectName(_ROLE_TO_OBJECT_NAME.get(role, "PrimaryBtn"))
    if fixed_size is not None:
        btn.setFixedSize(*fixed_size)
    else:
        btn.setFixedHeight(fixed_height)
    btn.setFocusPolicy(QtCore.Qt.StrongFocus)
    btn.setAutoDefault(False)
    btn.setDefault(False)
    btn.clicked.connect(slot)
    return btn
