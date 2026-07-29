"""
test_tracker - 工作状态追踪器单元测试
========================================

覆盖 src/core/tracker.py 的 WorkTrackerCore 状态机，重点测试：
- check_start_recorded：上班回溯（优先级 1-4）
- poll：轮询事件判定（off / target_reached / working / idle / back）
- manual_off_work：手动下班
- resume_after_off：下班后恢复
- reset_for_new_day：跨天重置

WorkTrackerCore 是纯逻辑（不写 DB），测试时直接传参构造场景。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.core.tracker import WorkTrackerCore


@pytest.fixture
def tracker() -> WorkTrackerCore:
    """构造测试用 tracker 实例。"""
    return WorkTrackerCore()


class TestCheckStartRecorded:
    """check_start_recorded：上班回溯（4 个优先级）。"""

    def test_priority_1_existing_manual_record_not_overwritten(
        self, tracker: WorkTrackerCore
    ) -> None:
        """优先级 1：已有手动记录 → 不覆盖，返回 None。"""
        now = datetime(2026, 7, 15, 9, 30, 0)
        existing_start = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.check_start_recorded(
            now=now,
            work_start_floor="06:00",
            existing_start=existing_start,
            existing_source="manual",
        )
        assert result is None
        assert tracker.is_started() is True

    def test_priority_2_existing_auto_record_not_overwritten(
        self, tracker: WorkTrackerCore
    ) -> None:
        """优先级 2：已有自动记录 → 不覆盖，返回 None。"""
        now = datetime(2026, 7, 15, 9, 30, 0)
        existing_start = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.check_start_recorded(
            now=now,
            work_start_floor="06:00",
            existing_start=existing_start,
            existing_source="auto",
        )
        assert result is None
        assert tracker.is_started() is True

    def test_priority_3_backfill_from_first_active(self, tracker: WorkTrackerCore) -> None:
        """优先级 3：无记录 + 有最早活跃记录 → 回填上班时间。"""
        now = datetime(2026, 7, 15, 10, 0, 0)
        first_active = datetime(2026, 7, 15, 8, 45, 0)  # 早于 9:00
        result = tracker.check_start_recorded(
            now=now,
            work_start_floor="09:00",
            existing_start=None,
            existing_source=None,
            first_active=first_active,
        )
        assert result == datetime(2026, 7, 15, 9, 0, 0)  # 对齐到 09:00
        assert tracker.is_started() is True

    def test_priority_3_first_active_after_floor(self, tracker: WorkTrackerCore) -> None:
        """优先级 3：最早活跃记录晚于 floor → 用实际时间。"""
        now = datetime(2026, 7, 15, 10, 0, 0)
        first_active = datetime(2026, 7, 15, 9, 30, 0)  # 晚于 09:00
        result = tracker.check_start_recorded(
            now=now,
            work_start_floor="09:00",
            existing_start=None,
            existing_source=None,
            first_active=first_active,
        )
        assert result == datetime(2026, 7, 15, 9, 30, 0)
        assert tracker.is_started() is True

    def test_priority_4_no_record_no_active(self, tracker: WorkTrackerCore) -> None:
        """优先级 4：无记录 + 无活跃记录 → 返回 None，静默等待。"""
        now = datetime(2026, 7, 15, 10, 0, 0)
        result = tracker.check_start_recorded(
            now=now,
            work_start_floor="06:00",
            existing_start=None,
            existing_source=None,
            first_active=None,
        )
        assert result is None
        assert tracker.is_started() is False


class TestPoll:
    """poll：轮询事件判定。

    事件类型：off / target_reached / working / idle / back / manual_off
    """

    def test_off_event_hidle_away(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """下班事件：HID 空闲超阈值 + 达时间下限。"""
        # mock HID 读取：空闲 2 小时（>60分钟阈值）
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 7200.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: False)
        monkeypatch.setattr(
            "src.core.tracker.get_last_active_time",
            lambda idle, now: now - timedelta(seconds=7200),
        )

        now = datetime(2026, 7, 15, 20, 0, 0)  # 20:00，超过 19:00 下限
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "off"
        assert result.off_time is not None

    def test_off_event_before_time_floor_not_triggered(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """下班未触发：HID 空闲超阈值但未达时间下限。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 7200.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: False)
        monkeypatch.setattr(
            "src.core.tracker.get_last_active_time",
            lambda idle, now: now - timedelta(seconds=7200),
        )

        now = datetime(2026, 7, 15, 18, 0, 0)  # 18:00，未达 19:00 下限
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        # 18:00 未达 19:00 下限，不触发 off
        assert result.event != "off"

    def test_target_reached_event(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """达标事件：worked_hours >= daily_required_hours。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 30.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: True)
        monkeypatch.setattr("src.core.tracker.get_last_active_time", lambda idle, now: now)

        now = datetime(2026, 7, 15, 17, 30, 0)  # 17:30，从 9:00 起已工作 8.5h
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "target_reached"
        assert result.worked_hours == 8.5

    def test_working_state(self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch) -> None:
        """工作中状态：未下班、未达标、HID 活跃。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 30.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: True)
        monkeypatch.setattr("src.core.tracker.get_last_active_time", lambda idle, now: now)

        now = datetime(2026, 7, 15, 14, 0, 0)  # 14:00，从 9:00 起已工作 5h
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "working"
        assert result.worked_hours == 5.0
        assert result.start_time == start_time

    def test_idle_state_no_start_time(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """空闲状态：无上班时间。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 30.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: True)
        monkeypatch.setattr("src.core.tracker.get_last_active_time", lambda idle, now: now)

        now = datetime(2026, 7, 15, 8, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=None,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "idle"

    def test_back_event_after_off(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """下班后回来活跃 → back 事件。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 30.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: True)
        monkeypatch.setattr("src.core.tracker.get_last_active_time", lambda idle, now: now)

        # 先手动下班
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )
        assert tracker.is_off() is True

        # 再 poll：用户回来活跃 → back 事件
        now = datetime(2026, 7, 15, 18, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            daily_end_time=datetime(2026, 7, 15, 17, 0, 0),
            daily_source="manual",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "back"

    def test_back_event_only_once(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """back 事件只触发一次（防重复弹窗）。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 30.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: True)
        monkeypatch.setattr("src.core.tracker.get_last_active_time", lambda idle, now: now)

        # 手动下班
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )

        # 第一次 poll → back 事件
        now = datetime(2026, 7, 15, 18, 0, 0)
        result1 = tracker.poll(
            now=now,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            daily_end_time=datetime(2026, 7, 15, 17, 0, 0),
            daily_source="manual",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result1.event == "back"

        # 第二次 poll → idle（不再 back）
        result2 = tracker.poll(
            now=now,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            daily_end_time=datetime(2026, 7, 15, 17, 0, 0),
            daily_source="manual",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result2.event == "idle"


class TestManualOffWork:
    """manual_off_work：手动下班。"""

    def test_manual_off_returns_off_event(self, tracker: WorkTrackerCore) -> None:
        """手动下班返回 manual_off 事件。"""
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        now = datetime(2026, 7, 15, 17, 30, 0)
        result = tracker.manual_off_work(start_time=start_time, now=now)
        assert result.event == "manual_off"
        assert result.off_time == now
        assert result.worked_hours == 8.5
        assert tracker.is_off() is True

    def test_manual_off_default_now(self, tracker: WorkTrackerCore) -> None:
        """手动下班默认用 datetime.now()（不传 now 参数）。"""
        # 用默认 now 参数
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.manual_off_work(start_time=start_time)
        assert result.event == "manual_off"
        assert result.off_time is not None
        assert tracker.is_off() is True


class TestResumeAfterOff:
    """resume_after_off：下班后恢复。"""

    def test_resume_resets_off_state(self, tracker: WorkTrackerCore) -> None:
        """恢复后 is_off() 返回 False。"""
        # 先手动下班
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )
        assert tracker.is_off() is True

        # 恢复
        tracker.resume_after_off()
        assert tracker.is_off() is False

    def test_resume_allows_off_again(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """恢复后可再次下班。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 7200.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: False)
        monkeypatch.setattr(
            "src.core.tracker.get_last_active_time",
            lambda idle, now: now - timedelta(seconds=7200),
        )

        # 第一次下班
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )
        assert tracker.is_off() is True

        # 恢复
        tracker.resume_after_off()
        assert tracker.is_off() is False

        # 再次下班（HID 空闲超阈值）
        now = datetime(2026, 7, 15, 20, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "off"


class TestResetForNewDay:
    """reset_for_new_day：跨天重置。"""

    def test_reset_clears_all_state(self, tracker: WorkTrackerCore) -> None:
        """重置后所有状态标记归零。"""
        # 先手动下班（设置 _manual_off 标志）
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )
        assert tracker.is_off() is True

        # 重置
        tracker.reset_for_new_day()
        assert tracker.is_started() is False
        assert tracker.is_off() is False
        assert tracker.last_idle is None

    def test_reset_allows_new_day_start(
        self, tracker: WorkTrackerCore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """重置后新一天可重新上班。"""
        monkeypatch.setattr("src.core.tracker.get_hid_idle_seconds", lambda: 30.0)
        monkeypatch.setattr("src.core.tracker.is_currently_active", lambda idle: True)
        monkeypatch.setattr("src.core.tracker.get_last_active_time", lambda idle, now: now)

        # 第一天下班
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )

        # 跨天重置
        tracker.reset_for_new_day()

        # 新一天 poll（无上班记录）→ idle 状态
        now = datetime(2026, 7, 16, 8, 0, 0)
        result = tracker.poll(
            now=now,
            start_time=None,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        assert result.event == "idle"
