"""
test_settings_service - 设置服务单元测试
==========================================

覆盖 src/services/settings_service.py 的 SettingsService：
- init：启动迁移 + 加载缓存
- get：读取类型化设置（带缓存）
- update：更新字段并持久化
- reload：强制从 DB 重新加载
- 默认值处理
- 解析失败的降级处理
"""

from __future__ import annotations

import pytest

from src.data.settings_repo import SettingsRepository
from src.services.settings_service import Settings, SettingsService


@pytest.fixture
def service(tmp_db) -> SettingsService:
    """构造测试用 SettingsService（用 tmp_db 初始化的 DB）。"""
    repo = SettingsRepository(db_path=str(tmp_db))
    return SettingsService(repo)


class TestSettings:
    """Settings dataclass 基本测试。"""

    def test_default_values(self) -> None:
        """默认值正确。"""
        s = Settings()
        assert s.daily_required_hours == 8.0
        assert s.weekly_work_days == 5
        assert s.off_threshold_minutes == 60.0
        assert s.off_time_floor == "19:00"
        assert s.work_start_floor == "06:00"
        assert s.notify_on_target is True
        assert s.notify_on_off is True
        assert s.auto_start is False
        assert s.holiday_auto_exclude is True
        assert s.auto_update is False
        assert s.office_network_domain == ""
        assert s.only_office_time is False
        assert s.last_update_check == ""


class TestInit:
    """init：启动迁移 + 加载缓存。"""

    def test_init_returns_settings(self, service: SettingsService) -> None:
        """init 返回 Settings 实例。"""
        result = service.init()
        assert isinstance(result, Settings)
        # 默认值（tmp_db 初始化时写入了 DEFAULT_SETTINGS）
        assert result.daily_required_hours == 8.0
        assert result.weekly_work_days == 5

    def test_init_caches_settings(self, service: SettingsService) -> None:
        """init 后 get 返回缓存实例。"""
        s1 = service.init()
        s2 = service.get()
        assert s1 is s2  # 同一引用（缓存）


class TestGet:
    """get：读取类型化设置。"""

    def test_get_without_init_loads_from_db(self, service: SettingsService) -> None:
        """未 init 时 get 自动从 DB 加载。"""
        result = service.get()
        assert isinstance(result, Settings)
        assert result.daily_required_hours == 8.0

    def test_get_returns_cached(self, service: SettingsService) -> None:
        """get 返回缓存。"""
        s1 = service.get()
        s2 = service.get()
        assert s1 is s2


class TestUpdate:
    """update：更新字段并持久化。"""

    def test_update_single_field(self, service: SettingsService) -> None:
        """更新单个字段。"""
        service.update(daily_required_hours=9.0)
        result = service.get()
        assert result.daily_required_hours == 9.0

    def test_update_multiple_fields(self, service: SettingsService) -> None:
        """更新多个字段。"""
        service.update(
            daily_required_hours=9.0,
            weekly_work_days=6,
            notify_on_target=False,
        )
        result = service.get()
        assert result.daily_required_hours == 9.0
        assert result.weekly_work_days == 6
        assert result.notify_on_target is False

    def test_update_persists_to_db(self, service: SettingsService, tmp_db) -> None:
        """更新后持久化到 DB。"""
        service.update(daily_required_hours=9.0)

        # 用新 repo 读 DB，验证持久化
        new_repo = SettingsRepository(db_path=str(tmp_db))
        assert new_repo.get("daily_required_hours") == "9.0"

    def test_update_bool_field_persists_as_string(self, service: SettingsService, tmp_db) -> None:
        """bool 字段持久化为 "1"/"0" 字符串。"""
        service.update(notify_on_target=False)
        new_repo = SettingsRepository(db_path=str(tmp_db))
        assert new_repo.get("notify_on_target") == "0"

    def test_update_unknown_field_raises(self, service: SettingsService) -> None:
        """更新未知字段抛 ValueError。"""
        with pytest.raises(ValueError, match="未知的设置字段"):
            service.update(unknown_field=123)

    def test_update_refreshes_cache(self, service: SettingsService) -> None:
        """更新后缓存刷新。"""
        old = service.get()
        service.update(daily_required_hours=9.0)
        new = service.get()
        assert old is not new  # 不是同一引用（replace 生成新对象）
        assert new.daily_required_hours == 9.0


class TestReload:
    """reload：强制从 DB 重新加载。"""

    def test_reload_clears_cache(self, service: SettingsService, tmp_db) -> None:
        """reload 从 DB 重新加载。"""
        service.init()
        # 直接改 DB（绕过 service 缓存）
        repo = SettingsRepository(db_path=str(tmp_db))
        repo.set("daily_required_hours", "10.0")

        # reload 前缓存还是旧值
        assert service.get().daily_required_hours == 8.0

        # reload 后读到 DB 新值
        result = service.reload()
        assert result.daily_required_hours == 10.0


class TestParseFailure:
    """解析失败的降级处理。"""

    def test_parse_failure_uses_default(self, tmp_db) -> None:
        """DB 值解析失败时用默认值。"""
        # 直接写一个非法值到 DB
        repo = SettingsRepository(db_path=str(tmp_db))
        repo.set("daily_required_hours", "not_a_number")

        service = SettingsService(repo)
        result = service.init()
        # 解析失败，降级为默认值 8.0
        assert result.daily_required_hours == 8.0
