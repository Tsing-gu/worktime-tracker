"""
settings_service - 设置服务
============================

封装 SettingsRepository，向上提供类型化的设置读写 + 启动迁移机制。

核心职责:
    - init():           启动迁移 + 加载缓存
    - get() -> Settings: 读取类型化设置（带缓存）
    - update(**kwargs):    更新设置字段并持久化
    - _migrate_legacy_keys(): 迁移老 key 到新 key（当前 no-op，机制就位）

设计说明:
    现有 13 个 setting key 命名已相当规范（snake_case + 语义清晰），
    故当前不实际重命名，但迁移机制就位，后续改名时直接用。
    老用户 key 原样保留，零迁移成本。

版本: 0.16.0
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from typing import Any

from src.config import DEFAULT_SETTINGS
from src.data.settings_repo import SettingsRepository

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """
    类型化设置模型。

    把 settings 表的 13 个 key 映射为带类型的字段，
    上层用 `settings.daily_required_hours`（float）替代 `float(repo.get(KEY))`。

    字段类型与 DB 存储格式（字符串）的转换由 SettingsService 处理。
    """

    # ─── 工时要求 ───
    daily_required_hours: float = 8.0
    weekly_work_days: int = 5

    # ─── 下班判定 ───
    off_threshold_minutes: float = 60.0
    off_time_floor: str = "19:00"
    work_start_floor: str = "06:00"

    # ─── 通知开关 ───
    notify_on_target: bool = True
    notify_on_off: bool = True

    # ─── 系统行为 ───
    auto_start: bool = False
    holiday_auto_exclude: bool = True
    auto_update: bool = False

    # ─── 网络门控 ───
    office_network_domain: str = ""
    only_office_time: bool = False

    # ─── 更新检查（非用户设置，记录上次检查时间）───
    last_update_check: str = ""


# ─── key ↔ 字段名映射 + 类型转换 ───────────────────────────

# DB key → dataclass 字段名（当前 1:1 映射，后续改名时这里做转换）
_KEY_TO_FIELD: dict[str, str] = {
    "daily_required_hours": "daily_required_hours",
    "weekly_work_days": "weekly_work_days",
    "off_threshold_minutes": "off_threshold_minutes",
    "off_time_floor": "off_time_floor",
    "work_start_floor": "work_start_floor",
    "notify_on_target": "notify_on_target",
    "notify_on_off": "notify_on_off",
    "auto_start": "auto_start",
    "holiday_auto_exclude": "holiday_auto_exclude",
    "auto_update": "auto_update",
    "last_update_check": "last_update_check",
    "office_network_domain": "office_network_domain",
    "only_office_time": "only_office_time",
}

# 字段名 → DB key（反向映射）
_FIELD_TO_KEY: dict[str, str] = {v: k for k, v in _KEY_TO_FIELD.items()}

# 字段名 → 类型转换函数（DB 字符串 → Python 类型）
# 统一用 Callable[[str], Any]，int/float/str 作为 callable 也能调用
_FIELD_PARSERS: dict[str, Callable[[str], object]] = {
    "daily_required_hours": float,
    "weekly_work_days": int,
    "off_threshold_minutes": float,
    "off_time_floor": str,
    "work_start_floor": str,
    "notify_on_target": lambda v: v == "1",
    "notify_on_off": lambda v: v == "1",
    "auto_start": lambda v: v == "1",
    "holiday_auto_exclude": lambda v: v == "1",
    "auto_update": lambda v: v == "1",
    "last_update_check": str,
    "office_network_domain": str,
    "only_office_time": lambda v: v == "1",
}

# 字段名 → 序列化函数（Python 类型 → DB 字符串）
_FIELD_SERIALIZERS: dict[str, Callable[[object], str]] = {
    "daily_required_hours": lambda v: str(v),
    "weekly_work_days": lambda v: str(v),
    "off_threshold_minutes": lambda v: str(v),
    "off_time_floor": lambda v: v if isinstance(v, str) else str(v),
    "work_start_floor": lambda v: v if isinstance(v, str) else str(v),
    "notify_on_target": lambda v: "1" if v else "0",
    "notify_on_off": lambda v: "1" if v else "0",
    "auto_start": lambda v: "1" if v else "0",
    "holiday_auto_exclude": lambda v: "1" if v else "0",
    "auto_update": lambda v: "1" if v else "0",
    "last_update_check": lambda v: v if isinstance(v, str) else str(v),
    "office_network_domain": lambda v: v if isinstance(v, str) else str(v),
    "only_office_time": lambda v: "1" if v else "0",
}


class SettingsService:
    """设置服务，封装 SettingsRepository，提供类型化读写 + 启动迁移。

    Args:
        settings_repo: SettingsRepository 实例
    """

    def __init__(self, settings_repo: SettingsRepository) -> None:
        self._repo = settings_repo
        self._cache: Settings | None = None
        self._on_changed_callbacks: list[Callable[[], None]] = []

    def register_on_changed(self, callback: Callable[[], None]) -> None:
        """注册设置变更回调，update() 后依次调用。用于通知依赖设置的服务刷新缓存。"""
        self._on_changed_callbacks.append(callback)

    def init(self) -> Settings:
        """启动迁移 + 加载缓存。

        Returns:
            加载好的 Settings 实例
        """
        self._migrate_legacy_keys()
        self._cache = self._load_from_db()
        logger.info("设置服务初始化完成")
        return self._cache

    def get(self) -> Settings:
        """读取设置（带缓存）。

        Returns:
            Settings 实例
        """
        if self._cache is None:
            self._cache = self._load_from_db()
        return self._cache

    def update(self, **kwargs: Any) -> Settings:
        """更新设置字段并持久化。

        只更新传入的字段，其他字段保持不变。
        更新后刷新缓存。

        Args:
            **kwargs: 要更新的字段（如 daily_required_hours=9.0）

        Returns:
            更新后的 Settings 实例
        """
        current = self.get()
        # 校验字段名合法
        valid_fields = {f.name for f in fields(Settings)}
        for key in kwargs:
            if key not in valid_fields:
                raise ValueError(f"未知的设置字段：{key}")

        # 持久化到 DB
        for field_name, value in kwargs.items():
            db_key = _FIELD_TO_KEY[field_name]
            serializer = _FIELD_SERIALIZERS[field_name]
            self._repo.set(db_key, serializer(value))

        # 刷新缓存
        self._cache = replace(current, **kwargs)
        logger.debug("设置已更新：%s", kwargs)
        # 通知依赖方（如 StatsService 的计算器缓存失效）
        for cb in self._on_changed_callbacks:
            cb()
        return self._cache

    def reload(self) -> Settings:
        """强制从 DB 重新加载（清除缓存）。"""
        self._cache = self._load_from_db()
        return self._cache

    # ─── 内部方法 ──────────────────────────────────────────

    def _migrate_legacy_keys(self) -> None:
        """迁移老 key 到新 key（当前 no-op，机制就位）。

        后续若要重命名 key，在此添加迁移逻辑：
            1. 检查老 key 是否存在
            2. 若存在且新 key 为默认值，则把老 key 的值写入新 key
            3. 删除老 key（可选，避免残留）
        迁移幂等可重入，中途崩溃不影响下次启动。
        """
        # 当前无 key 重命名需求，此方法为 no-op
        logger.debug("设置迁移完成（当前无迁移项）")

    def _load_from_db(self) -> Settings:
        """从 DB 加载全部设置，构造 Settings 实例。"""
        db_values = self._repo.get_all()
        field_values: dict[str, Any] = {}

        for db_key, field_name in _KEY_TO_FIELD.items():
            raw = db_values.get(db_key, DEFAULT_SETTINGS.get(db_key, ""))
            parser = _FIELD_PARSERS[field_name]
            try:
                field_values[field_name] = parser(raw)
            except (ValueError, TypeError) as e:
                logger.warning("设置 %s 解析失败（值=%r），使用默认值：%s", db_key, raw, e)
                # 用默认值
                field_values[field_name] = self._get_default(field_name)

        return Settings(**field_values)

    def _get_default(self, field_name: str) -> Any:
        """获取字段的默认值。"""
        defaults = Settings()
        return getattr(defaults, field_name)

    # ─── UI 层兼容方法（Phase 3 迁移期保留） ──────────────

    def get_settings_dict(self) -> dict[str, str]:
        """读取全部设置为 dict（UI 层 SettingsDialog 兼容用）。

        返回 {key: value} 的原始字符串 dict，与旧 WorktimeService.get_settings() 行为一致。
        """
        return self._repo.get_all()

    def update_from_dict(self, values: dict[str, str]) -> None:
        """从 dict 批量更新设置（UI 层 SettingsDialog 兼容用）。

        values 是 {key: value} 的原始字符串 dict，与旧 WorktimeService.update_settings() 行为一致。
        直接写 DB，不走类型化 update()（因为 SettingsDialog 传的是字符串）。
        """
        for key, value in values.items():
            self._repo.set(key, value)
        self._cache = self._load_from_db()
        for cb in self._on_changed_callbacks:
            cb()
        logger.debug("设置已批量更新（dict 模式）：%s", values)

    def get_setting(self, key: str, default: str = "") -> str:
        """读取单个设置值（原始字符串，UI 层兼容用）。"""
        return self._repo.get(key, default)
