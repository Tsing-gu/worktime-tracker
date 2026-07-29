"""
test_settings_repo - 设置仓储单元测试
========================================

覆盖 src/data/settings_repo.py 的 SettingsRepository：
- get：读取单个设置值
- set：写入或更新设置值（upsert 语义）
- get_all：读取全部设置

用 tmp_db fixture 隔离数据库。
"""

from __future__ import annotations

import pytest

from src.data.settings_repo import SettingsRepository


@pytest.fixture
def repo(tmp_db) -> SettingsRepository:
    """构造测试用 repo 实例。tmp_db 已初始化默认设置。"""
    return SettingsRepository(db_path=str(tmp_db))


class TestGet:
    """get：读取单个设置值。"""

    def test_get_existing_setting(self, repo: SettingsRepository) -> None:
        """读取已存在的设置（默认值）。"""
        # tmp_db 初始化时写入了 DEFAULT_SETTINGS
        result = repo.get("daily_required_hours")
        assert result == "8.0"

    def test_get_nonexistent_returns_default(self, repo: SettingsRepository) -> None:
        """读取不存在的 key 返回默认值。"""
        result = repo.get("nonexistent_key", default="fallback")
        assert result == "fallback"

    def test_get_nonexistent_returns_empty(self, repo: SettingsRepository) -> None:
        """读取不存在的 key 默认返回空串。"""
        result = repo.get("nonexistent_key")
        assert result == ""


class TestSet:
    """set：写入或更新设置值。"""

    def test_set_new_value(self, repo: SettingsRepository) -> None:
        """写入新值。"""
        repo.set("custom_key", "custom_value")
        assert repo.get("custom_key") == "custom_value"

    def test_set_overwrite_existing(self, repo: SettingsRepository) -> None:
        """覆盖已有值。"""
        # 默认值是 "8.0"
        assert repo.get("daily_required_hours") == "8.0"

        repo.set("daily_required_hours", "9.0")
        assert repo.get("daily_required_hours") == "9.0"

    def test_set_then_get_all(self, repo: SettingsRepository) -> None:
        """set 后 get_all 包含新值。"""
        repo.set("new_key", "new_value")
        all_settings = repo.get_all()
        assert "new_key" in all_settings
        assert all_settings["new_key"] == "new_value"


class TestGetAll:
    """get_all：读取全部设置。"""

    def test_returns_dict(self, repo: SettingsRepository) -> None:
        """返回 dict 类型。"""
        result = repo.get_all()
        assert isinstance(result, dict)

    def test_contains_default_settings(self, repo: SettingsRepository) -> None:
        """包含初始化的默认设置。"""
        result = repo.get_all()
        # 验证几个默认 key
        assert "daily_required_hours" in result
        assert "weekly_work_days" in result
        assert "off_threshold_minutes" in result

    def test_get_all_empty_after_no_init(self, tmp_path) -> None:
        """未初始化的数据库 get_all 抛 OperationalError（表不存在）。

        这是预期行为：Repository 必须先调用 Repository.init() 初始化表结构，
        未初始化的 DB 查询会因表不存在而抛 sqlite3.OperationalError。
        """
        from src.data.settings_repo import SettingsRepository

        # 用一个未初始化的 DB 路径（不调用 Repository.init）
        db_path = tmp_path / "empty.db"
        repo = SettingsRepository(db_path=str(db_path))
        with pytest.raises(Exception):  # noqa: B017
            repo.get_all()
