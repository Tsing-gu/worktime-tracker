# -*- coding: utf-8 -*-
"""
system - macOS 系统调用封装
=============================

统一封装所有需要调用外部系统命令的操作：
    - ioreg:    读取 HIDIdleTime（键鼠空闲时长）
    - pmset:    读取电源管理日志（回溯上班时间）
    - osascript: 发送 macOS 系统通知

版本: 0.4.2
"""

import subprocess
import re
from datetime import datetime, timedelta
from typing import Optional

from src.config import ACTIVE_THRESHOLD_SECONDS, AWAY_THRESHOLD_SECONDS


# ─── HID 空闲时间 ─────────────────────────────────────────────

def get_hid_idle_seconds() -> float:
    """
    通过 `ioreg -c IOHIDSystem` 读取 HIDIdleTime（键鼠空闲时长）。

    HIDIdleTime 是纳秒级整数，表示自最后一次键鼠操作以来的空闲时长。
    返回秒为单位的浮点数。读取失败返回 -1.0。

    Returns:
        空闲时长（秒），或 -1.0 表示读取失败
    """
    result = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True)
    for line in result.stdout.split("\n"):
        if "HIDIdleTime" in line:
            match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', line)
            if match:
                ns = int(match.group(1))
                return ns / 1e9  # 纳秒 → 秒
    return -1.0


def is_currently_active(idle_seconds: float, active_threshold: float = ACTIVE_THRESHOLD_SECONDS) -> bool:
    """
    判断当前是否有键鼠活动。

    Args:
        idle_seconds:      HIDIdleTime（秒）
        active_threshold:  活动判定阈值（秒），空闲 < 此值视为正在操作

    Returns:
        True=有活动, False=空闲
    """
    return 0 <= idle_seconds < active_threshold


def is_user_away(idle_seconds: float, away_threshold: float = AWAY_THRESHOLD_SECONDS) -> bool:
    """
    判断用户是否已离开电脑。

    Args:
        idle_seconds:    HIDIdleTime（秒）
        away_threshold:  离开判定阈值（秒），空闲 > 此值视为离开

    Returns:
        True=用户已离开, False=仍在使用
    """
    return idle_seconds > away_threshold


def get_last_active_time(idle_seconds: float, now: datetime = None) -> Optional[datetime]:
    """
    根据空闲时长回推最后一次键鼠活动时刻。

    last_active = now - idle_seconds

    Args:
        idle_seconds: HIDIdleTime（秒）
        now:          当前时间（默认 datetime.now()）

    Returns:
        最后一次活动时刻，或 None（空闲值为负表示读取失败）
    """
    if now is None:
        now = datetime.now()
    if idle_seconds < 0:
        return None
    return now - timedelta(seconds=idle_seconds)


# ─── pmset 电源日志 ───────────────────────────────────────────

def get_first_active_from_pmset(work_date, work_start_floor: str = "06:00") -> Optional[datetime]:
    """
    从 `pmset -g log` 日志中回溯当天上班检测起始时间后首次 UserIsActive 事件。

    用于程序启动时校验/回填上班时间，比 HIDIdleTime 更准确。

    Args:
        work_date:        目标工作日
        work_start_floor:  上班检测起始时间 "HH:MM"

    Returns:
        首次 UserIsActive 事件时间，或 None
    """
    try:
        result = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None

    date_str = work_date.isoformat()
    # 匹配 pmset 日志中的 UserIsActive 断言创建行
    pattern = re.compile(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \+\d{4}\s+Assertions\s+PID \d+\(.*?\) (?:Created|TurnedOn) UserIsActive'
    )

    floor_h, floor_m = map(int, work_start_floor.split(":"))

    first_active = None
    for line in result.stdout.split("\n"):
        if date_str not in line:
            continue
        m = pattern.match(line)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            # 验证归属工作日是否匹配
            from src.core.date_utils import compute_work_date
            work_dt = compute_work_date(ts)
            if work_dt != work_date:
                continue
            # 过滤早于上班检测起始时间的事件
            if ts.hour < floor_h or (ts.hour == floor_h and ts.minute < floor_m):
                continue
            # 取最早的一条
            if first_active is None or ts < first_active:
                first_active = ts

    return first_active


# ─── macOS 系统通知 ───────────────────────────────────────────

def send_notification(title: str, message: str, sound: str = "Glass"):
    """
    通过 osascript 发送 macOS 系统通知。

    Args:
        title:   通知标题
        message: 通知正文
        sound:   通知声音名称（默认 "Glass"）
    """
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}" sound name "{sound}"'],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass
