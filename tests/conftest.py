"""
conftest - pytest 共享 fixture
================================

提供跨测试的共享 fixture：
- tmp_db：隔离的 SQLite 数据库环境，测试结束自动清理
- sample_holidays：典型节假日数据（含放假日 + 调休补班日）
- sample_records：典型每日工时记录（已工作 / 已下班 / 请假 / 无记录）

所有 fixture 用 tmp_path 隔离，不污染真实 DB（~/.worktime_tracker/worktime.db）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离的 SQLite 数据库环境。

    创建临时 DB 目录，monkeypatch 覆盖 config.DB_PATH 和 database 模块的 DB_PATH，
    初始化表结构，返回 DB 文件路径。测试结束自动清理（tmp_path 机制）。

    Returns:
        临时 DB 文件路径
    """
    db_dir = tmp_path / ".worktime_tracker"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "worktime.db"

    # monkeypatch 覆盖 DB_PATH（Repository.init 类方法用到）
    monkeypatch.setattr("src.config.DB_PATH", str(db_path))
    monkeypatch.setattr("src.config.DB_DIR", str(db_dir))
    monkeypatch.setattr("src.data.database.DB_PATH", str(db_path))

    # 初始化表结构
    from src.data.database import Repository

    Repository.init(str(db_path))

    return db_path


@pytest.fixture
def sample_holidays() -> list[dict[str, Any]]:
    """典型节假日数据（2026 年示例）。

    包含：
    - 元旦（放假日）
    - 春节假期（放假日 + 调休补班日）
    - 普通周末不算在内（由 is_workday 按 weekly_work_days 判定）

    Returns:
        节假日 dict 列表，每项含 date / name / is_off_day
    """
    return [
        # 元旦放假
        {"date": "2026-01-01", "name": "元旦", "is_off_day": True},
        # 春节放假（1月26日-2月1日）
        {"date": "2026-01-26", "name": "春节", "is_off_day": True},
        {"date": "2026-01-27", "name": "春节", "is_off_day": True},
        {"date": "2026-01-28", "name": "春节", "is_off_day": True},
        {"date": "2026-01-29", "name": "春节", "is_off_day": True},
        {"date": "2026-01-30", "name": "春节", "is_off_day": True},
        {"date": "2026-01-31", "name": "春节", "is_off_day": True},
        {"date": "2026-02-01", "name": "春节", "is_off_day": True},
        {"date": "2026-02-02", "name": "春节", "is_off_day": True},
        # 春节前调休补班（周六日补班）
        {"date": "2026-01-24", "name": "春节调休", "is_off_day": False},
        {"date": "2026-02-07", "name": "春节调休", "is_off_day": False},
    ]


@pytest.fixture
def sample_records() -> list[dict[str, Any]]:
    """典型每日工时记录（一周示例，2026-07-13 周一到 2026-07-19 周日）。

    包含：
    - 周一：已下班，工时 8.5h，达标
    - 周二：已下班，工时 7.5h，未达标
    - 周三：工作中，无 end_time（实时计算工时）
    - 周四：请假（年假）
    - 周五：无记录
    - 周六/周日：周末（不在 records 里，由 is_workday 判定非工作日）

    Returns:
        每日工时记录 dict 列表
    """
    dt_format = "%Y-%m-%d %H:%M:%S"
    return [
        {
            "work_date": "2026-07-13",
            "start_time": datetime(2026, 7, 13, 9, 0, 0).strftime(dt_format),
            "end_time": datetime(2026, 7, 13, 17, 30, 0).strftime(dt_format),
            "total_hours": 8.5,
            "required_hours": 8.0,
            "leave_type": None,
            "is_confirmed": 1,
            "has_anomaly": 0,
            "anomaly_note": None,
            "source": "auto",
            "note": None,
        },
        {
            "work_date": "2026-07-14",
            "start_time": datetime(2026, 7, 14, 9, 15, 0).strftime(dt_format),
            "end_time": datetime(2026, 7, 14, 16, 45, 0).strftime(dt_format),
            "total_hours": 7.5,
            "required_hours": 8.0,
            "leave_type": None,
            "is_confirmed": 1,
            "has_anomaly": 0,
            "anomaly_note": None,
            "source": "auto",
            "note": None,
        },
        {
            "work_date": "2026-07-15",
            "start_time": datetime(2026, 7, 15, 9, 30, 0).strftime(dt_format),
            "end_time": None,
            "total_hours": None,
            "required_hours": 8.0,
            "leave_type": None,
            "is_confirmed": 0,
            "has_anomaly": 0,
            "anomaly_note": None,
            "source": "auto",
            "note": None,
        },
        {
            "work_date": "2026-07-16",
            "start_time": None,
            "end_time": None,
            "total_hours": None,
            "required_hours": 8.0,
            "leave_type": "annual",
            "is_confirmed": 1,
            "has_anomaly": 0,
            "anomaly_note": None,
            "source": "auto",
            "note": "请假-年假",
        },
    ]


@pytest.fixture
def fixed_now() -> datetime:
    """固定的「当前时间」用于测试（2026-07-15 14:00:00 周三下午）。

    避免测试依赖真实时间，确保结果可复现。
    """
    return datetime(2026, 7, 15, 14, 0, 0)
