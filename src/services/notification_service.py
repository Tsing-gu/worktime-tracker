# -*- coding: utf-8 -*-
"""
notification_service - 通知服务
=================================

封装 macOS 系统通知逻辑，提供工时相关的通知 API。
底层调用 utils.system.send_notification (osascript)。

版本: 0.4.2
"""

from src.utils.system import send_notification


def notify_off_work(off_time_str: str, worked_hours: float):
    """
    下班提醒通知。

    Args:
        off_time_str: 下班时间字符串（如 "18:30"）
        worked_hours: 今日工时（小时）
    """
    send_notification(
        "下班提醒",
        f"检测到您已离开，下班时间：{off_time_str}，今日工时 {worked_hours:.1f} 小时",
    )


def notify_target_reached(worked_hours: float, required: float):
    """
    工时达标提醒通知。

    Args:
        worked_hours: 当前已工作时长（小时）
        required:     每日工时要求（小时）
    """
    send_notification(
        "工时达标",
        f"今日已工作 {worked_hours:.1f} 小时，达到目标 {required:.1f} 小时，可以下班啦！",
    )
