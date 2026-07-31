"""
test_system - 系统调用封装单测
================================

覆盖 src/utils/system.py 的纯函数：
- get_active_periods_from_pmset：解析 pmset 日志的 UserIsActive 事件
- get_first_active_from_pmset：复用 get_active_periods_from_pmset[0]
- get_hid_idle_seconds / is_currently_active / is_user_away / get_last_active_time
- get_network_status

用 monkeypatch 替换 subprocess.run，mock pmset 日志输出。
"""

from __future__ import annotations

import subprocess
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.utils.system import (
    get_active_periods_from_pmset,
    get_first_active_from_pmset,
    get_hid_idle_seconds,
    get_last_active_time,
    get_network_status,
    is_currently_active,
    is_user_away,
)


def _make_pmset_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    """构造一个像 subprocess.run 返回的 mock。"""
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.stdout = stdout
    r.returncode = returncode
    return r


class TestGetActivePeriodsFromPmset:
    """get_active_periods_from_pmset：解析 pmset 日志的首次/末次 UserIsActive。"""

    def test_normal_day_returns_first_and_last(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """单日日志返回首次和末次 UserIsActive。"""
        log = (
            '2026-07-30 09:30:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 12:00:00 +0800 Assertions            PID 54500(WindowServer) TurnedOn UserIsActive "..."\n'
            '2026-07-30 18:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 22:00:00 +0800 Assertions            PID 54500(WindowServer) TurnedOn UserIsActive "..."\n'
        )
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "06:00")
        assert first == datetime(2026, 7, 30, 9, 30, 0)
        assert last == datetime(2026, 7, 30, 22, 0, 0)

    def test_filters_events_before_work_start_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """早于 work_start_floor 的事件不计入 first_active。"""
        log = (
            '2026-07-30 05:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 09:30:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 18:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
        )
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "06:00")
        # first 不包含 05:00
        assert first == datetime(2026, 7, 30, 9, 30, 0)
        # last 包含所有事件（无时间下限）
        assert last == datetime(2026, 7, 30, 18, 0, 0)

    def test_cross_day_event_belongs_to_previous_work_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """凌晨 1 点的活动归属前一天工作日（6:00 窗口规则）。

        - 查 2026-07-29：01:00 归属 2026-07-29，但早于 floor 06:00 → first=None
          （01:00 不应算作上班时间），last=01:00（last 无时间下限，反映深夜加班）
        - 查 2026-07-30：01:00 不归属 2026-07-30 → 被过滤
        """
        log = (
            '2026-07-30 01:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 09:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 22:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
        )
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        # 查 2026-07-29：01:00 归属前一天，但早于 floor → first=None，last=01:00
        first, last = get_active_periods_from_pmset(date(2026, 7, 29), "06:00")
        assert first is None  # 凌晨 1 点不应算作上班时间
        assert last == datetime(2026, 7, 30, 1, 0, 0)  # 但算作最后活动（深夜加班）

        # 查 2026-07-30：09:00 / 22:00 归属今天，01:00 不归属
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "06:00")
        assert first == datetime(2026, 7, 30, 9, 0, 0)
        assert last == datetime(2026, 7, 30, 22, 0, 0)

    def test_no_matching_events_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """没有匹配的 UserIsActive 事件时返回 (None, None)。"""
        log = '2026-07-30 09:00:00 +0800 Assertions            PID 363(powerd) Summary PreventUserIdleSystemSleep "..."\n'
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "06:00")
        assert first is None
        assert last is None

    def test_only_events_before_floor_returns_no_first_but_last(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """全部事件早于 floor 时，first=None 但 last 有值（无时间下限）。

        用 work_start_floor="08:00" 让 07:00 的事件归属 2026-07-30 但早于 floor：
            - 07:00 hour=7 >= 6 → compute_work_date 归属 2026-07-30
            - 07:00 < floor 08:00 → first_active 过滤掉
            - last_active 无时间下限 → 保留 07:00
        """
        log = (
            '2026-07-30 06:30:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 07:00:00 +0800 Assertions            PID 54500(WindowServer) TurnedOn UserIsActive "..."\n'
        )
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "08:00")
        assert first is None
        assert last == datetime(2026, 7, 30, 7, 0, 0)

    def test_subprocess_failure_returns_none_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """subprocess.run 抛异常时返回 (None, None)。"""
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("pmset", 5)),
        )
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "06:00")
        assert first is None
        assert last is None

    def test_filters_other_dates_events(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """其他日期的事件不计入目标工作日。"""
        log = (
            '2026-07-29 09:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 09:30:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 18:00:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
        )
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        first, last = get_active_periods_from_pmset(date(2026, 7, 30), "06:00")
        assert first == datetime(2026, 7, 30, 9, 30, 0)
        assert last == datetime(2026, 7, 30, 18, 0, 0)


class TestGetFirstActiveFromPmset:
    """get_first_active_from_pmset：复用 get_active_periods_from_pmset[0]。"""

    def test_returns_first_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """返回首次 UserIsActive。"""
        log = (
            '2026-07-30 09:30:00 +0800 Assertions            PID 54500(WindowServer) Created UserIsActive "..."\n'
            '2026-07-30 22:00:00 +0800 Assertions            PID 54500(WindowServer) TurnedOn UserIsActive "..."\n'
        )
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        result = get_first_active_from_pmset(date(2026, 7, 30), "06:00")
        assert result == datetime(2026, 7, 30, 9, 30, 0)

    def test_returns_none_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无匹配事件时返回 None。"""
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=""),
        )
        result = get_first_active_from_pmset(date(2026, 7, 30), "06:00")
        assert result is None


class TestHidIdleSeconds:
    """get_hid_idle_seconds / is_currently_active / is_user_away / get_last_active_time。"""

    def test_get_hid_idle_seconds_parses_nanoseconds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """从 ioreg 输出解析 HIDIdleTime（纳秒 → 秒）。"""
        log = '"HIDIdleTime" = 5000000000\n'
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        assert get_hid_idle_seconds() == 5.0

    def test_get_hid_idle_seconds_returns_neg_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ioreg 失败返回 -1.0。"""
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("ioreg", 5)),
        )
        assert get_hid_idle_seconds() == -1.0

    def test_is_currently_active_threshold(self) -> None:
        """is_currently_active 按 active_threshold 判定。"""
        assert is_currently_active(1.0, active_threshold=5.0) is True
        assert is_currently_active(5.0, active_threshold=5.0) is False  # 等于阈值不算
        assert is_currently_active(10.0, active_threshold=5.0) is False
        assert is_currently_active(-1.0, active_threshold=5.0) is False  # 读取失败不算

    def test_is_user_away_threshold(self) -> None:
        """is_user_away 按 away_threshold 判定。"""
        assert is_user_away(400.0, away_threshold=300.0) is True
        assert is_user_away(100.0, away_threshold=300.0) is False
        assert is_user_away(-1.0, away_threshold=300.0) is False  # 读取失败不算

    def test_get_last_active_time(self) -> None:
        """get_last_active_time 从 now 反推。"""
        now = datetime(2026, 7, 30, 14, 0, 0)
        # idle=3600s → 1 小时前
        result = get_last_active_time(3600.0, now=now)
        assert result == now - timedelta(seconds=3600)

    def test_get_last_active_time_returns_none_on_failure(self) -> None:
        """读取失败（idle<0）返回 None。"""
        assert get_last_active_time(-1.0) is None


class TestNetworkStatus:
    """get_network_status：检测公司内网。"""

    def test_at_office_when_domain_matches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """domain_search 包含 office_domain → at_office=True。"""
        log = "domain_search { corp.kuaishou.com kuaishou.com }\n"
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        result = get_network_status("corp.kuaishou.com")
        assert result["at_office"] is True
        assert "corp.kuaishou.com" in result["domain"]

    def test_not_at_office_when_domain_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """domain_search 不包含 office_domain → at_office=False。"""
        log = "domain_search { home.router.local }\n"
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        result = get_network_status("corp.kuaishou.com")
        assert result["at_office"] is False

    def test_not_at_office_when_no_domain_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ipconfig 无 domain_search → at_office=False。"""
        log = "some other line without domain_search\n"
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: _make_pmset_result(stdout=log),
        )
        result = get_network_status("corp.kuaishou.com")
        assert result["at_office"] is False
        assert result["domain"] == ""

    def test_subprocess_failure_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ipconfig 调用失败返回 at_office=False。"""
        monkeypatch.setattr(
            "src.utils.system.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("ipconfig", 3)),
        )
        result = get_network_status("corp.kuaishou.com")
        assert result["at_office"] is False
        assert result["domain"] == ""

    def test_uses_default_route_interface(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """优先使用默认路由接口，而不是固定 en0。"""
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[:4] == ["route", "-n", "get", "default"]:
                return _make_pmset_result(stdout="interface: en1\n")
            if args[:2] == ["ifconfig", "-l"]:
                return _make_pmset_result(stdout="lo0 en0 en1\n")
            if args[:3] == ["ipconfig", "getpacket", "en1"]:
                return _make_pmset_result(stdout="domain_search { corp.example }\n")
            return _make_pmset_result(stdout="")

        monkeypatch.setattr("src.utils.system.subprocess.run", fake_run)
        result = get_network_status("corp.example")

        assert result["at_office"] is True
        assert ["ipconfig", "getpacket", "en1"] in calls
        assert ["ipconfig", "getpacket", "en0"] not in calls
