"""
test_worktime_repo - 每日工时仓储单元测试
==========================================

覆盖 src/data/worktime_repo.py 的 DailyWorktimeRepository：
- get：查询指定日期记录
- upsert：插入或更新（含 _UNSET 哨兵语义）
- get_range：范围查询
- delete：删除记录
- clear_end_time：清除下班时间

用 tmp_db fixture 隔离数据库，不污染真实 DB。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.data.worktime_repo import DailyWorktimeRepository


@pytest.fixture
def repo(tmp_db) -> DailyWorktimeRepository:
    """构造测试用 repo 实例（用 tmp_db 隔离的数据库路径）。"""
    return DailyWorktimeRepository(db_path=str(tmp_db))


class TestGet:
    """get：查询指定日期记录。"""

    def test_get_nonexistent_returns_none(self, repo: DailyWorktimeRepository) -> None:
        """查询不存在的日期返回 None。"""
        result = repo.get(date(2026, 7, 15))
        assert result is None

    def test_get_existing_record(self, repo: DailyWorktimeRepository) -> None:
        """查询已存在的记录。"""
        work_date = date(2026, 7, 15)
        start = datetime(2026, 7, 15, 9, 0, 0)
        repo.upsert(work_date, start_time=start, source="auto")

        result = repo.get(work_date)
        assert result is not None
        assert result["work_date"] == "2026-07-15"
        assert result["start_time"] == "2026-07-15 09:00:00"
        assert result["source"] == "auto"


class TestUpsert:
    """upsert：插入或更新（含 _UNSET 哨兵语义）。"""

    def test_insert_new_record(self, repo: DailyWorktimeRepository) -> None:
        """插入新记录。"""
        work_date = date(2026, 7, 15)
        start = datetime(2026, 7, 15, 9, 0, 0)
        end = datetime(2026, 7, 15, 17, 30, 0)
        repo.upsert(
            work_date,
            start_time=start,
            end_time=end,
            total_hours=8.5,
            required_hours=8.0,
            source="auto",
        )

        result = repo.get(work_date)
        assert result is not None
        assert result["start_time"] == "2026-07-15 09:00:00"
        assert result["end_time"] == "2026-07-15 17:30:00"
        assert result["total_hours"] == 8.5
        assert result["required_hours"] == 8.0
        assert result["source"] == "auto"

    def test_update_existing_record(self, repo: DailyWorktimeRepository) -> None:
        """更新已有记录（只传部分字段，其他字段不变）。"""
        work_date = date(2026, 7, 15)
        start = datetime(2026, 7, 15, 9, 0, 0)
        # 先插入
        repo.upsert(work_date, start_time=start, source="auto")

        # 再更新（加 end_time）
        end = datetime(2026, 7, 15, 17, 30, 0)
        repo.upsert(work_date, end_time=end, total_hours=8.5)

        result = repo.get(work_date)
        assert result is not None
        assert result["start_time"] == "2026-07-15 09:00:00"  # 原值保留
        assert result["end_time"] == "2026-07-15 17:30:00"  # 新值
        assert result["total_hours"] == 8.5

    def test_unset_fields_not_modified(self, repo: DailyWorktimeRepository) -> None:
        """未传入的字段（_UNSET）不被修改。"""
        work_date = date(2026, 7, 15)
        start = datetime(2026, 7, 15, 9, 0, 0)
        end = datetime(2026, 7, 15, 17, 0, 0)
        repo.upsert(work_date, start_time=start, end_time=end, total_hours=8.0)

        # 更新 required_hours，其他字段不应被清空
        repo.upsert(work_date, required_hours=9.0)

        result = repo.get(work_date)
        assert result is not None
        assert result["start_time"] == "2026-07-15 09:00:00"  # 保留
        assert result["end_time"] == "2026-07-15 17:00:00"  # 保留
        assert result["total_hours"] == 8.0  # 保留
        assert result["required_hours"] == 9.0  # 新值

    def test_upsert_leave_type(self, repo: DailyWorktimeRepository) -> None:
        """upsert 请假记录。"""
        work_date = date(2026, 7, 16)
        repo.upsert(work_date, leave_type="annual", note="请假-年假")

        result = repo.get(work_date)
        assert result is not None
        assert result["leave_type"] == "annual"
        assert result["note"] == "请假-年假"

    def test_upsert_is_confirmed(self, repo: DailyWorktimeRepository) -> None:
        """upsert 确认状态。"""
        work_date = date(2026, 7, 15)
        repo.upsert(work_date, start_time=datetime(2026, 7, 15, 9, 0, 0))
        repo.upsert(work_date, is_confirmed=1)

        result = repo.get(work_date)
        assert result is not None
        assert result["is_confirmed"] == 1


class TestGetRange:
    """get_range：范围查询。"""

    def test_empty_range(self, repo: DailyWorktimeRepository) -> None:
        """空范围查询返回空列表。"""
        result = repo.get_range(date(2026, 7, 1), date(2026, 7, 10))
        assert result == []

    def test_range_with_records(self, repo: DailyWorktimeRepository) -> None:
        """范围查询含多条记录，按 work_date 升序排列。"""
        # 插入 3 条记录（乱序插入）
        repo.upsert(date(2026, 7, 15), start_time=datetime(2026, 7, 15, 9, 0, 0))
        repo.upsert(date(2026, 7, 13), start_time=datetime(2026, 7, 13, 9, 0, 0))
        repo.upsert(date(2026, 7, 14), start_time=datetime(2026, 7, 14, 9, 0, 0))

        result = repo.get_range(date(2026, 7, 13), date(2026, 7, 15))
        assert len(result) == 3
        # 验证升序排列
        assert result[0]["work_date"] == "2026-07-13"
        assert result[1]["work_date"] == "2026-07-14"
        assert result[2]["work_date"] == "2026-07-15"

    def test_range_excludes_outside(self, repo: DailyWorktimeRepository) -> None:
        """范围查询排除范围外的记录。"""
        repo.upsert(date(2026, 7, 12), start_time=datetime(2026, 7, 12, 9, 0, 0))
        repo.upsert(date(2026, 7, 13), start_time=datetime(2026, 7, 13, 9, 0, 0))
        repo.upsert(date(2026, 7, 16), start_time=datetime(2026, 7, 16, 9, 0, 0))

        result = repo.get_range(date(2026, 7, 13), date(2026, 7, 15))
        assert len(result) == 1
        assert result[0]["work_date"] == "2026-07-13"


class TestDelete:
    """delete：删除记录。"""

    def test_delete_existing(self, repo: DailyWorktimeRepository) -> None:
        """删除已存在的记录。"""
        work_date = date(2026, 7, 15)
        repo.upsert(work_date, start_time=datetime(2026, 7, 15, 9, 0, 0))
        assert repo.get(work_date) is not None

        repo.delete(work_date)
        assert repo.get(work_date) is None

    def test_delete_nonexistent_silent(self, repo: DailyWorktimeRepository) -> None:
        """删除不存在的记录不报错。"""
        repo.delete(date(2026, 7, 15))  # 不应抛异常


class TestClearEndTime:
    """clear_end_time：清除下班时间。"""

    def test_clear_end_time(self, repo: DailyWorktimeRepository) -> None:
        """清除下班时间，恢复为工作中状态。"""
        work_date = date(2026, 7, 15)
        repo.upsert(
            work_date,
            start_time=datetime(2026, 7, 15, 9, 0, 0),
            end_time=datetime(2026, 7, 15, 17, 0, 0),
            total_hours=8.0,
        )

        repo.clear_end_time(work_date)

        result = repo.get(work_date)
        assert result is not None
        assert result["end_time"] is None
        assert result["total_hours"] is None
        assert result["start_time"] == "2026-07-15 09:00:00"  # 保留

    def test_clear_end_time_nonexistent_silent(self, repo: DailyWorktimeRepository) -> None:
        """清除不存在的记录不报错。"""
        repo.clear_end_time(date(2026, 7, 15))  # 不应抛异常
