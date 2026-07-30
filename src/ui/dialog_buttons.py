"""
dialog_buttons - 对话框按钮封装
================================

避免 QDialogButtonBox 在 macOS 上的焦点链问题（点击非默认按钮后焦点
自动切到默认按钮，导致点击事件被吞），统一用自定义 QPushButton + 手动
clicked.connect 替代。

核心 API:
    - make_dialog_button(text, role, slot) -> QPushButton
    - make_ok_cancel_buttons(ok_text, cancel_text, on_ok, on_cancel) -> QHBoxLayout

版本: 0.16.3
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtWidgets


def make_dialog_button(
    text: str,
    role: str,
    slot: Callable[[], None],
) -> QtWidgets.QPushButton:
    """创建对话框按钮（避免 QDialogButtonBox 焦点链问题）。

    统一配置:
        - setObjectName: PrimaryBtn / SecondaryBtn（QSS 主题样式）
        - setFixedHeight(32): 统一高度
        - setFocusPolicy(StrongFocus): 可接收焦点
        - setAutoDefault(False) + setDefault(False): 彻底关闭默认按钮行为

    Args:
        text: 按钮文字
        role: "primary"（确定类，主操作）/ "secondary"（取消类，次要操作）
        slot: 点击回调，通常是 dialog.accept / dialog.reject

    Returns:
        配置好的 QPushButton 实例
    """
    btn = QtWidgets.QPushButton(text)
    btn.setObjectName("PrimaryBtn" if role == "primary" else "SecondaryBtn")
    btn.setFixedHeight(32)
    btn.setFocusPolicy(QtCore.Qt.StrongFocus)
    btn.setAutoDefault(False)
    btn.setDefault(False)
    btn.clicked.connect(slot)
    return btn


def make_ok_cancel_buttons(
    ok_text: str = "确定",
    cancel_text: str = "取消",
    on_ok: Callable[[], None] | None = None,
    on_cancel: Callable[[], None] | None = None,
) -> QtWidgets.QHBoxLayout:
    """创建 OK/Cancel 按钮对，返回布局（右对齐，取消在左、确定在右）。

    Args:
        ok_text:     确定按钮文字（默认"确定"）
        cancel_text:  取消按钮文字（默认"取消"）
        on_ok:       确定回调（通常是 dialog.accept），None 则不连接
        on_cancel:   取消回调（通常是 dialog.reject），None 则不连接

    Returns:
        QHBoxLayout：addStretch + cancel_btn + ok_btn，直接 addLayout 到对话框布局
    """
    layout = QtWidgets.QHBoxLayout()
    layout.addStretch()
    cancel_btn = make_dialog_button(
        cancel_text, "secondary", on_cancel if on_cancel else lambda: None
    )
    ok_btn = make_dialog_button(ok_text, "primary", on_ok if on_ok else lambda: None)
    layout.addWidget(cancel_btn)
    layout.addWidget(ok_btn)
    return layout
