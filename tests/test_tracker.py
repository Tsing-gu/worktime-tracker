"""
test_tracker - 工作状态追踪器单元测试
========================================

覆盖 src/core/tracker.py 的 WorkTrackerCore 状态机，重点测试：
- check_start_recorded：上班回溯（优先级 1-4）
- poll：轮询事件判定（off / target_reached / working / idle / back）
- manual_off_work：手动下班
- resume_after_off：下班后恢复
- reset_for_new_day：跨天重置

WorkTrackerCore 是纯逻辑（不写 DB、不读 I/O）：
- poll() 接收 idle 参数，由调用方读取 HID 后传入
- is_currently_active / get_last_active_time 是纯函数，依据 idle 自动派生
- 测试直接传参构造场景，无需 monkeypatch 系统调用
"""

from __future__ import annotations

from datetime import datetime

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

    def test_off_event_hidle_away(self, tracker: WorkTrackerCore) -> None:
        """下班事件：HID 空闲超阈值 + 达时间下限。"""
        now = datetime(2026, 7, 15, 20, 0, 0)  # 20:00，超过 19:00 下限
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            idle=7200.0,  # 空闲 2 小时（>60分钟阈值）→ active=False
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

    def test_off_event_before_time_floor_not_triggered(self, tracker: WorkTrackerCore) -> None:
        """下班未触发：HID 空闲超阈值但未达时间下限。"""
        now = datetime(2026, 7, 15, 18, 0, 0)  # 18:00，未达 19:00 下限
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            idle=7200.0,  # 空闲 2 小时（超阈值）
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

    def test_target_reached_event(self, tracker: WorkTrackerCore) -> None:
        """达标事件：worked_hours >= daily_required_hours。"""
        now = datetime(2026, 7, 15, 17, 30, 0)  # 17:30，从 9:00 起已工作 8.5h
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            idle=3.0,  # 正在操作（< 5 秒阈值）→ active=True
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

    def test_working_state(self, tracker: WorkTrackerCore) -> None:
        """工作中状态：未下班、未达标、HID 活跃。"""
        now = datetime(2026, 7, 15, 14, 0, 0)  # 14:00，从 9:00 起已工作 5h
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            idle=3.0,  # 正在操作
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

    def test_idle_state_no_start_time(self, tracker: WorkTrackerCore) -> None:
        """空闲状态：无上班时间。"""
        now = datetime(2026, 7, 15, 8, 0, 0)
        result = tracker.poll(
            now=now,
            idle=3.0,
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

    def test_back_event_after_off(self, tracker: WorkTrackerCore) -> None:
        """下班后回来活跃 → back 事件。"""
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
            idle=3.0,  # 正在操作（< 5 秒阈值）→ active=True 触发 back
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

    def test_back_event_only_once(self, tracker: WorkTrackerCore) -> None:
        """back 事件只触发一次（防重复弹窗）。"""
        # 手动下班
        tracker.manual_off_work(
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            now=datetime(2026, 7, 15, 17, 0, 0),
        )

        # 第一次 poll → back 事件
        now = datetime(2026, 7, 15, 18, 0, 0)
        result1 = tracker.poll(
            now=now,
            idle=3.0,
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
            idle=3.0,
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

    # ─── 参数化事件矩阵 ────────────────────────────────────

    @pytest.mark.parametrize(
        "idle, at_office, only_office, expected_event",
        [
            # 活跃 + 在公司 → 未下班，达工时 → target_reached
            pytest.param(0.0, True, False, "target_reached", id="active-at-office-0s"),
            pytest.param(3.0, True, False, "target_reached", id="active-at-office-3s"),
            # 活跃 + 不在公司 + only_office → office_away → off
            pytest.param(3.0, False, True, "off", id="active-away-office-only"),
            # 活跃 + 不在公司 + !only_office → office_away 不生效 → target_reached
            pytest.param(3.0, False, False, "target_reached", id="active-away-no-only"),
            # 活跃 + 在公司 + only_office → office_away 不生效 → target_reached
            pytest.param(3.0, True, True, "target_reached", id="active-at-office-only"),
            # 空闲 30 分钟（未达 60 分钟阈值）→ hid_away=False → target_reached
            pytest.param(1800.0, True, False, "target_reached", id="idle-30min-no-off"),
            # 空闲刚过 60 分钟阈值 → hid_away=True → off
            pytest.param(3700.0, True, False, "off", id="idle-just-over-threshold"),
            # 空闲 + 不在公司 + only_office → hid_away + office_away → off
            pytest.param(3700.0, False, True, "off", id="idle-away-office-only"),
            # 空闲 2 小时 → hid_away → off
            pytest.param(7200.0, True, False, "off", id="idle-2h"),
            # 空闲 2 小时 + !only_office + 不在公司 → hid_away → off（only_office 不影响）
            pytest.param(7200.0, False, False, "off", id="idle-2h-no-only"),
        ],
    )
    def test_poll_event_matrix(
        self,
        tracker: WorkTrackerCore,
        idle: float,
        at_office: bool,
        only_office: bool,
        expected_event: str,
    ) -> None:
        """参数化测试：idle × at_office × only_office 事件判定矩阵。

        固定 now=20:00（达 19:00 下限），start_time=09:00（worked=11h 已达标），
        覆盖 hid_away / office_away 两条下班路径与 target_reached 的边界。
        """
        now = datetime(2026, 7, 15, 20, 0, 0)
        start_time = datetime(2026, 7, 15, 9, 0, 0)
        result = tracker.poll(
            now=now,
            idle=idle,
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=at_office,
            only_office=only_office,
        )
        assert result.event == expected_event

    def test_off_not_triggered_before_time_floor(self, tracker: WorkTrackerCore) -> None:
        """HID 空闲超阈值但未达时间下限 → 不触发 off，走 target_reached。"""
        now = datetime(2026, 7, 15, 18, 0, 0)  # 18:00，未达 19:00 下限
        start_time = datetime(2026, 7, 15, 9, 0, 0)  # worked=9h（已达标）
        result = tracker.poll(
            now=now,
            idle=7200.0,  # 空闲 2 小时（超阈值）
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        # 未达 19:00 下限，不触发 off；worked=9h>=8h → target_reached
        assert result.event == "target_reached"

    def test_off_triggered_early_morning(self, tracker: WorkTrackerCore) -> None:
        """凌晨时段（0:00-6:00）HID 空闲超阈值 → 直接触发 off（不要求 off_time_floor）。"""
        now = datetime(2026, 7, 16, 3, 0, 0)  # 凌晨 3:00
        start_time = datetime(2026, 7, 15, 9, 0, 0)  # 前一天上班，worked=18h
        result = tracker.poll(
            now=now,
            idle=7200.0,  # 空闲 2 小时（超阈值）
            start_time=start_time,
            daily_end_time=None,
            daily_source="auto",
            off_threshold_minutes=60,
            off_time_floor="19:00",
            daily_required_hours=8.0,
            at_office=True,
            only_office=False,
        )
        # 凌晨时段直接判定 off（is_early_morning=True，不要求 off_floor_met）
        assert result.event == "off"


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

    def test_resume_allows_off_again(self, tracker: WorkTrackerCore) -> None:
        """恢复后可再次下班。"""
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
            idle=7200.0,  # 空闲 2 小时（超阈值）
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

    def test_reset_allows_new_day_start(self, tracker: WorkTrackerCore) -> None:
        """重置后新一天可重新上班。"""
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
            idle=3.0,
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
