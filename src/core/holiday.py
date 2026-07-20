# -*- coding: utf-8 -*-
"""
holiday - 节假日 API 获取 + 本地缓存
======================================

从 GitHub NateScarlet/holiday-cn 项目获取中国法定节假日数据，
支持 GitHub raw 主 URL + jsDelivr CDN 备用 + 本地 JSON 缓存容灾。

数据写入数据库 holidays 表（由 service 层调用 database.save_holidays）。

版本: 0.4.2
"""

import json
import os
import urllib.request
from datetime import date
from pathlib import Path

from src.config import HOLIDAY_API_URLS, HOLIDAY_CACHE_FILE
from src.data import database


def fetch_holidays(year: int) -> list:
    """
    从 API 获取指定年份的中国节假日数据。

    尝试顺序:
        1. GitHub raw URL（主）
        2. jsDelivr CDN URL（备）
        3. 本地 JSON 缓存（容灾）

    获取成功后写入 DB 和本地缓存。

    Args:
        year: 年份（如 2026）

    Returns:
        节假日列表（每项含 date/name/isOffDay），空列表表示全部失败
    """
    for url_template in HOLIDAY_API_URLS:
        url = url_template.format(year=year)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            days = data.get("days", [])
            # 写入 DB 缓存（按年份增量写入，不影响其他年份）
            database.save_holiday_year(year, days)
            # 写入本地文件缓存
            _save_cache(year, days)
            return days
        except Exception:
            continue

    # 所有 API 失败 → 尝试本地缓存
    cached = _load_cache(year)
    if cached:
        database.save_holiday_year(year, cached)
        return cached

    return []


def _save_cache(year: int, days: list):
    """
    将节假日数据保存到本地 JSON 缓存文件。

    缓存文件路径: ~/.worktime_tracker/holiday_cache.json
    结构: {"2026": [...], "2025": [...]}

    Args:
        year: 年份
        days: 节假日列表
    """
    Path(os.path.dirname(HOLIDAY_CACHE_FILE)).mkdir(parents=True, exist_ok=True)
    cache = {}
    if os.path.exists(HOLIDAY_CACHE_FILE):
        try:
            with open(HOLIDAY_CACHE_FILE, "r") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    cache[str(year)] = days
    with open(HOLIDAY_CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False)


def _load_cache(year: int) -> list:
    """
    从本地 JSON 缓存文件读取指定年份的节假日数据。

    Args:
        year: 年份

    Returns:
        节假日列表，空列表表示无缓存
    """
    if not os.path.exists(HOLIDAY_CACHE_FILE):
        return []
    try:
        with open(HOLIDAY_CACHE_FILE, "r") as f:
            cache = json.load(f)
        return cache.get(str(year), [])
    except Exception:
        return []


def ensure_holidays_loaded(year: int) -> list:
    """
    确保指定年份的节假日数据已加载到 DB。

    如果 DB 中已有该年数据 → 直接返回；
    否则 → 从 API 获取并写入 DB。

    Args:
        year: 年份

    Returns:
        节假日列表
    """
    existing = database.get_all_holidays()
    if existing:
        # 检查 DB 中是否包含目标年份
        years_in_db = set()
        for h in existing:
            y = int(h["date"][:4])
            years_in_db.add(y)
        if year in years_in_db:
            return existing

    return fetch_holidays(year)


def is_holiday(dt: date) -> bool:
    """
    判断指定日期是否为放假日。

    Args:
        dt: 日期

    Returns:
        True=放假日, False=非放假日
    """
    h = database.get_holiday(dt)
    return h is not None and h["is_off_day"] == 1


def is_adjusted_workday(dt: date) -> bool:
    """
    判断指定日期是否为调休上班日（周末补班）。

    Args:
        dt: 日期

    Returns:
        True=调休上班日, False=非调休上班日
    """
    h = database.get_holiday(dt)
    return h is not None and h["is_off_day"] == 0
