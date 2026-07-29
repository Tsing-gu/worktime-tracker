"""
test_activity_repo - 活动事件仓储单元测试
==========================================

覆盖 src/data/activity_repo.py 的 ActivityRepository：
- record：记录活动事件
- get_today：查询指定工作日的全部活动
- get_first_active：最早活跃记录
- get_last_active_at_office：最后在公司活跃记录
- cleanup：清理过期记录

用 tmp_db fixture 隔离数据库。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.data.activity_repo import ActivityRepository


@pytest.fixture
def repo(tmp_db) -> ActivityRepository:
    """构造测试用 repo 实例。"""
    return ActivityRepository(db_path=str(tmp_db))


class TestRecord:
    """record：记录活动事件。"""

    def test_record_active_event(self, repo: ActivityRepository) -> None:
        """记录活跃事件（idle < 5s）。"""
        ts = datetime(2026, 7, 15, 9, 0, 0)
        repo.record(ts, idle_seconds=2.5, is_active=True, at_office=True)

        events = repo.get_today(date(2026, 7, 15))
        assert len(events) == 1
        assert events[0]["idle_seconds"] == 2.5
        assert events[0]["is_active"] == 1
        assert events[0]["at_office"] == 1

    def test_record_idle_event(self, repo: ActivityRepository) -> None:
        """记录空闲事件（idle > 5min）。"""
        ts = datetime(2026, 7, 15, 12, 0, 0)
        repo.record(ts, idle_seconds=1800.0, is_active=False, at_office=False)

        events = repo.get_today(date(2026, 7, 15))
        assert len(events) == 1
        assert events[0]["is_active"] == 0
        assert events[0]["at_office"] == 0

    def test_record_work_date_before_6am(self, repo: ActivityRepository) -> None:
        """6:00 之前的记录归属前一天。"""
        ts = datetime(2026, 7, 15, 5, 30, 0)  # 6:00 之前
        repo.record(ts, idle_seconds=2.0, is_active=True)

        # 归属前一天
        events = repo.get_today(date(2026, 7, 14))
        assert len(events) == 1
        # 今天无记录
        assert repo.get_today(date(2026, 7, 15)) == []


class TestGetFirstActive:
    """get_first_active：最早活跃记录。"""

    def test_no_active_returns_none(self, repo: ActivityRepository) -> None:
        """无活跃记录返回 None。"""
        result = repo.get_first_active(date(2026, 7, 15))
        assert result is None

    def test_returns_earliest_active(self, repo: ActivityRepository) -> None:
        """返回最早的活跃记录时间。"""
        # 插入 3 条活跃记录（乱序）
        repo.record(datetime(2026, 7, 15, 11, 0, 0), 1.0, True)
        repo.record(datetime(2026, 7, 15, 9, 0, 0), 1.0, True)  # 最早
        repo.record(datetime(2026, 7, 15, 10, 0, 0), 1.0, True)

        result = repo.get_first_active(date(2026, 7, 15))
        assert result == datetime(2026, 7, 15, 9, 0, 0)

    def test_excludes_idle_events(self, repo: ActivityRepository) -> None:
        """排除空闲事件（is_active=0）。"""
        repo.record(datetime(2026, 7, 15, 8, 0, 0), 1800.0, False)  # 空闲
        repo.record(datetime(2026, 7, 15, 9, 0, 0), 1.0, True)  # 活跃

        result = repo.get_first_active(date(2026, 7, 15))
        assert result == datetime(2026, 7, 15, 9, 0, 0)  # 排除 8:00 的空闲

    def test_at_office_only_filter(self, repo: ActivityRepository) -> None:
        """at_office_only=True 只查在公司活跃记录。"""
        repo.record(datetime(2026, 7, 15, 9, 0, 0), 1.0, True, at_office=False)
        repo.record(datetime(2026, 7, 15, 10, 0, 0), 1.0, True, at_office=True)

        # 不筛选 → 返回最早 9:00
        assert repo.get_first_active(date(2026, 7, 15)) == datetime(2026, 7, 15, 9, 0, 0)
        # 只查在公司 → 返回 10:00
        result = repo.get_first_active(date(2026, 7, 15), at_office_only=True)
        assert result == datetime(2026, 7, 15, 10, 0, 0)


class TestGetLastActiveAtOffice:
    """get_last_active_at_office：最后在公司活跃记录。"""

    def test_no_records_returns_none(self, repo: ActivityRepository) -> None:
        """无记录返回 None。"""
        result = repo.get_last_active_at_office(date(2026, 7, 15))
        assert result is None

    def test_returns_latest_office_active(self, repo: ActivityRepository) -> None:
        """返回最后一条在公司活跃记录。"""
        repo.record(datetime(2026, 7, 15, 9, 0, 0), 1.0, True, at_office=True)
        repo.record(datetime(2026, 7, 15, 17, 0, 0), 1.0, True, at_office=True)  # 最后
        repo.record(datetime(2026, 7, 15, 18, 0, 0), 1.0, True, at_office=False)

        result = repo.get_last_active_at_office(date(2026, 7, 15))
        assert result == datetime(2026, 7, 15, 17, 0, 0)

    def test_excludes_non_office(self, repo: ActivityRepository) -> None:
        """排除不在公司的记录。"""
        repo.record(datetime(2026, 7, 15, 9, 0, 0), 1.0, True, at_office=True)
        repo.record(datetime(2026, 7, 15, 20, 0, 0), 1.0, True, at_office=False)  # 非公司

        result = repo.get_last_active_at_office(date(2026, 7, 15))
        assert result == datetime(2026, 7, 15, 9, 0, 0)


class TestCleanup:
    """cleanup：清理过期记录。"""

    def test_cleanup_removes_old_records(self, repo: ActivityRepository) -> None:
        """清理超过指定天数的记录。"""
        # 插入一条 20 天前的记录
        old_ts = datetime.now() - timedelta(days=20)
        repo.record(old_ts, 1.0, True)
        # 插入一条今天的记录
        repo.record(datetime.now(), 1.0, True)

        # 清理 14 天前的记录
        repo.cleanup(days=14)

        # 今天应该还有记录，20 天前的应被清理
        # 注意：cleanup 用 timestamp 比较，不是 work_date
        conn = repo._get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity_events")
        count = c.fetchone()[0]
        assert count == 1  # 只剩今天的
