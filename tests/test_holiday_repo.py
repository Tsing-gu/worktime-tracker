"""
test_holiday_repo - 节假日仓储单元测试
========================================

覆盖 src/data/holiday_repo.py 的 HolidayRepository：
- save_year：按年份增量写入节假日数据
- get：查询指定日期
- get_all：获取全部节假日

用 tmp_db fixture 隔离数据库。
"""

from __future__ import annotations

from datetime import date

import pytest

from src.data.holiday_repo import HolidayRepository


@pytest.fixture
def repo(tmp_db) -> HolidayRepository:
    """构造测试用 repo 实例。"""
    return HolidayRepository(db_path=str(tmp_db))


class TestSaveYear:
    """save_year：按年份增量写入节假日数据。"""

    def test_save_new_year(self, repo: HolidayRepository) -> None:
        """写入新年份的节假日。"""
        holidays = [
            {"date": "2026-01-01", "name": "元旦", "isOffDay": True},
            {"date": "2026-01-24", "name": "春节调休", "isOffDay": False},
        ]
        repo.save_year(2026, holidays)

        result = repo.get_all()
        assert len(result) == 2

    def test_save_replaces_same_year(self, repo: HolidayRepository) -> None:
        """重复写入同年份数据会替换旧数据。"""
        # 第一次写入
        repo.save_year(
            2026,
            [
                {"date": "2026-01-01", "name": "元旦", "isOffDay": True},
            ],
        )
        # 第二次写入同年份（不同数据）
        repo.save_year(
            2026,
            [
                {"date": "2026-01-01", "name": "元旦", "isOffDay": True},
                {"date": "2026-05-01", "name": "劳动节", "isOffDay": True},
            ],
        )

        result = repo.get_all()
        assert len(result) == 2  # 替换，不是累加

    def test_save_different_years_not_overwritten(self, repo: HolidayRepository) -> None:
        """写入不同年份不会覆盖其他年份。"""
        repo.save_year(
            2025,
            [
                {"date": "2025-01-01", "name": "元旦", "isOffDay": True},
            ],
        )
        repo.save_year(
            2026,
            [
                {"date": "2026-01-01", "name": "元旦", "isOffDay": True},
            ],
        )

        result = repo.get_all()
        assert len(result) == 2  # 两个年份都保留

    def test_isOffDay_field_conversion(self, repo: HolidayRepository) -> None:
        """isOffDay 字段（API 返回）正确转换为 is_off_day。"""
        holidays = [
            {"date": "2026-01-01", "name": "元旦", "isOffDay": True},  # 放假日
            {"date": "2026-01-24", "name": "调休", "isOffDay": False},  # 调休补班
        ]
        repo.save_year(2026, holidays)

        off_day = repo.get(date(2026, 1, 1))
        assert off_day is not None
        assert off_day["is_off_day"] == 1

        adjusted = repo.get(date(2026, 1, 24))
        assert adjusted is not None
        assert adjusted["is_off_day"] == 0


class TestGet:
    """get：查询指定日期。"""

    def test_get_nonexistent_returns_none(self, repo: HolidayRepository) -> None:
        """查询不存在的日期返回 None。"""
        result = repo.get(date(2026, 7, 15))
        assert result is None

    def test_get_existing_holiday(self, repo: HolidayRepository) -> None:
        """查询已存在的节假日。"""
        repo.save_year(
            2026,
            [
                {"date": "2026-01-01", "name": "元旦", "isOffDay": True},
            ],
        )

        result = repo.get(date(2026, 1, 1))
        assert result is not None
        assert result["date"] == "2026-01-01"
        assert result["name"] == "元旦"
        assert result["is_off_day"] == 1


class TestGetAll:
    """get_all：获取全部节假日。"""

    def test_empty_returns_empty_list(self, repo: HolidayRepository) -> None:
        """无数据返回空列表。"""
        result = repo.get_all()
        assert result == []

    def test_returns_all_sorted_by_date(self, repo: HolidayRepository) -> None:
        """返回全部节假日，按日期升序排列。"""
        repo.save_year(
            2026,
            [
                {"date": "2026-10-01", "name": "国庆", "isOffDay": True},
                {"date": "2026-01-01", "name": "元旦", "isOffDay": True},
                {"date": "2026-05-01", "name": "劳动节", "isOffDay": True},
            ],
        )

        result = repo.get_all()
        assert len(result) == 3
        # 验证升序排列
        assert result[0]["date"] == "2026-01-01"
        assert result[1]["date"] == "2026-05-01"
        assert result[2]["date"] == "2026-10-01"
