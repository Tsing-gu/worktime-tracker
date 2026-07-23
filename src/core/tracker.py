# -*- coding: utf-8 -*-
"""
tracker - 键鼠活动追踪 + 上下班判定
=====================================

本模块负责 HIDIdleTime 轮询逻辑和上下班判定算法。
**解耦设计**: tracker 不直接读写数据库，仅返回事件结果，
由 services.worktime_service 负责调用 database 持久化。

核心流程:
    1. poll() 读取 HIDIdleTime，判断活跃/空闲
    2. 检测上班条件（6:00 后首次键鼠活动）→ 返回 "start" 事件
    3. 检测下班条件（空闲超阈值 + 时间下限）→ 返回 "off" 事件
    4. 检测工时达标 → 返回 "target_reached" 事件
    5. 手动下班 → 返回 "manual_off" 事件
    6. 下班后用户回来活跃 → 返回 "back" 事件（UI 弹窗确认恢复）

版本: 0.4.2
"""

from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

from src.utils.system import (
    get_hid_idle_seconds,
    is_currently_active,
    get_last_active_time,
)
from src.config import ACTIVE_THRESHOLD_SECONDS


@dataclass
class PollResult:
    """
    单次轮询结果。

    每次调用 WorkTracker.poll() 返回此对象，
    包含事件类型和相关时间/工时数据。

    Attributes:
        event:        事件类型:
                      "start"          — 检测到上班
                      "off"            — 检测到下班
                      "manual_off"     — 手动下班
                      "back"           — 下班后用户回来活跃
                      "target_reached" — 工时达标
                      "working"        — 正常工作中
                      "idle"           — 空闲状态
        start_time:   上班时间（"start" 事件时有值）
        off_time:     下班时间（"off"/"manual_off" 事件时有值）
        worked_hours:  已工作时长（小时）
        idle:         当前 HIDIdleTime（秒）
        active:       当前是否有键鼠活动
        last_active:  最后一次活动时刻
    """
    event: str = "idle"
    start_time: Optional[datetime] = None
    off_time: Optional[datetime] = None
    worked_hours: float = 0.0
    idle: float = 0.0
    active: bool = False
    last_active: Optional[datetime] = None


class WorkTracker:
    """
    工作状态追踪器。

    维护上班/下班状态机的内部状态，通过 poll() 驱动状态转换。
    状态字段:
        - start_recorded:  是否已记录上班
        - off_notified:    是否已发送下班通知（防重复）
        - target_notified: 是否已发送达标通知（防重复）
        - manual_off:      是否已手动下班
        - back_notified:   是否已发送回来通知（防重复弹窗）

    调用方需自行管理持久化（database.record_activity / upsert_daily_worktime），
    tracker 仅返回 PollResult 供调用方决定如何处理。
    """

    def __init__(self):
        """初始化追踪器，所有状态标记归零。"""
        self.last_idle = None               # 上一次轮询的空闲值
        self._start_recorded = False         # 是否已记录上班
        self._off_notified = False           # 是否已通知下班
        self._target_notified = False        # 是否已通知达标
        self._manual_off = False             # 是否已手动下班
        self._back_notified = False          # 是否已发送回来通知（防重复弹窗）

    def is_started(self) -> bool:
        """是否已记录上班。"""
        return self._start_recorded

    def is_off(self) -> bool:
        """是否已下班（手动或自动）。"""
        return self._manual_off or self._off_notified

    # ─── 上班回溯 ──────────────────────────────────────────

    def check_start_recorded(self, now: datetime = None, work_start_floor: str = "06:00",
                              existing_start: Optional[datetime] = None,
                              existing_source: str = None,
                              existing_end_time: Optional[datetime] = None,
                              first_active: Optional[datetime] = None) -> Optional[datetime]:
        """
        校验或回溯当天上班时间（纯逻辑，不写 DB）。

        判定优先级:
            1. 已有手动记录 → 不覆盖
            2. 已有自动记录 → 不覆盖
            3. 无记录 + activity_events 有活跃记录 → 取最早活跃时间回填
            4. 以上都不满足 → 返回 None（暂不记录，等下一次轮询）

        Args:
            now:              当前时间
            work_start_floor: 上班检测起始时间 "HH:MM"
            existing_start:   DB 中已有的上班时间
            existing_source:  DB 中已有记录来源 'auto'/'manual'
            existing_end_time: DB 中已有下班时间
            first_active:     activity_events 中最早活跃记录的时间

        Returns:
            应记录的上班时间（需要写入 DB），或 None 表示无需操作
        """
        if now is None:
            now = datetime.now()

        floor_h, floor_m = map(int, work_start_floor.split(":"))

        # 优先级 1-2: 已有上班记录
        if existing_start:
            if existing_source == "manual":
                self._start_recorded = True
                return None

            self._start_recorded = True
            return None

        # 优先级 3: 无记录，从 activity_events 取最早活跃时间
        if first_active:
            start_time = first_active
            # 如果早于上班检测起始时间，对齐到起始时间
            if start_time.hour < floor_h or (start_time.hour == floor_h and start_time.minute < floor_m):
                start_time = start_time.replace(hour=floor_h, minute=floor_m, second=0, microsecond=0)
            self._start_recorded = True
            return start_time

        # 优先级 4: 以上都不满足 → 静默等待
        return None

    # ─── 轮询主逻辑 ────────────────────────────────────────

    def poll(
        self,
        now: datetime = None,
        start_time: Optional[datetime] = None,
        daily_end_time: Optional[datetime] = None,
        daily_source: str = "auto",
        off_threshold_minutes: float = 60,
        off_time_floor: str = "19:00",
        daily_required_hours: float = 8.0,
    ) -> PollResult:
        """
        执行一次轮询，返回事件结果（不写 DB）。

        事件判定顺序:
            1. 已下班（手动或自动）且用户回来活跃 → "back" 事件
            2. 已下班且用户未活跃 → "idle" 状态
            3. 有上班时间 + 未下班 + 空闲超阈值 + 达时间下限 → "off" 事件
            4. 有上班时间 + 未下班 + 工时达标 → "target_reached" 事件
            5. 有上班时间 + 未下班 + 正常工作中 → "working" 状态
            6. 其他 → "idle" 状态

        上班记录统一由 check_start_recorded() 处理，poll() 不再自行记录上班。

        Args:
            now:                     当前时间（默认 datetime.now()）
            start_time:              DB 中今日上班时间
            daily_end_time:          DB 中今日下班时间
            daily_source:            DB 中今日记录来源
            off_threshold_minutes:   下班判定等待时长（分钟）
            off_time_floor:          下班判定时间下限 "HH:MM"
            daily_required_hours:     每日工时要求（小时）

        Returns:
            PollResult 实例
        """
        if now is None:
            now = datetime.now()

        # 读取当前 HID 空闲时间
        idle = get_hid_idle_seconds()
        active = is_currently_active(idle)
        last_active = get_last_active_time(idle, now)

        self.last_idle = idle

        # ── 已下班（手动或自动）→ 检测用户是否回来 ──
        is_off = self._manual_off or (daily_end_time and daily_source == "manual") or self._off_notified
        if is_off:
            if self._manual_off or (daily_end_time and daily_source == "manual"):
                self._manual_off = True
            # 用户回来活跃 → 返回 back 事件（防重复弹窗）
            if active and not self._back_notified:
                self._back_notified = True
                return PollResult(event="back", idle=idle, active=active, last_active=last_active)
            # 用户未活跃 → 空闲状态
            return PollResult(event="idle", idle=idle, active=active, last_active=last_active)

        # ── 有上班时间 + 未下班 → 检测下班/达标 ──
        if start_time and not daily_end_time:
            worked_seconds = (now - start_time).total_seconds()
            worked_hours = worked_seconds / 3600.0

            away_threshold = off_threshold_minutes * 60  # 分钟 → 秒
            off_floor_h, off_floor_m = map(int, off_time_floor.split(":"))
            # 转为总分钟数比较（修复: 只比较小时导致分钟被忽略）
            now_total_min = now.hour * 60 + now.minute
            floor_total_min = off_floor_h * 60 + off_floor_m

            # ── 下班判定: 空闲超过阈值 ──
            if idle > away_threshold:
                off_time = last_active
                is_early_morning = now.hour < 6  # 凌晨时段（0:00~6:00，归属前一天工作日）

                # 凌晨时段不对齐 off_time（下班时间就是最后活动时间）
                if off_time and not is_early_morning:
                    off_total_min = off_time.hour * 60 + off_time.minute
                    if off_total_min < floor_total_min:
                        off_time = off_time.replace(hour=off_floor_h, minute=off_floor_m, second=0, microsecond=0)

                # 下班判定：已达时间下限，或凌晨时段直接判定
                off_floor_met = now_total_min >= floor_total_min
                if off_time and (off_floor_met or is_early_morning):
                    if not self._off_notified:
                        self._off_notified = True
                        return PollResult(
                            event="off",
                            off_time=off_time,
                            worked_hours=(off_time - start_time).total_seconds() / 3600.0,
                            idle=idle, active=active, last_active=last_active,
                        )

            # ── 达标判定: 工时达到要求 ──
            if worked_hours >= daily_required_hours and not self._target_notified:
                self._target_notified = True
                return PollResult(
                    event="target_reached",
                    worked_hours=worked_hours,
                    idle=idle, active=active, last_active=last_active,
                )

            # ── 正常工作中 ──
            return PollResult(
                event="working",
                start_time=start_time,
                worked_hours=worked_hours,
                idle=idle, active=active, last_active=last_active,
            )

        return PollResult(event="idle", idle=idle, active=active, last_active=last_active)

    # ─── 手动下班 ──────────────────────────────────────────

    def manual_off_work(self, start_time: datetime, now: datetime = None) -> PollResult:
        """
        手动下班：以当前时间记为下班时间（纯逻辑，不写 DB）。

        Args:
            start_time: 今日上班时间
            now:        当前时间（默认 datetime.now()）

        Returns:
            PollResult(event="manual_off", off_time=..., worked_hours=...)
        """
        if now is None:
            now = datetime.now()
        worked_hours = (now - start_time).total_seconds() / 3600.0
        self._manual_off = True
        return PollResult(event="manual_off", off_time=now, worked_hours=worked_hours)

    # ─── 恢复计时（下班后回来） ────────────────────────────

    def resume_after_off(self):
        """
        恢复计时状态：用户下班后回来，确认恢复。

        重置下班相关标记，使追踪器回到"工作中"状态。
        调用方应在调用此方法前/后清除 DB 中的 end_time。
        """
        self._off_notified = False
        self._manual_off = False
        self._back_notified = False

    # ─── 重置（跨天） ──────────────────────────────────────

    def reset_for_new_day(self):
        """
        重置追踪器状态，用于跨天时调用。
        所有状态标记归零，等待新一天的上下班判定。
        """
        self._start_recorded = False
        self._off_notified = False
        self._target_notified = False
        self._manual_off = False
        self._back_notified = False
        self.last_idle = None
