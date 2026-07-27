# -*- coding: utf-8 -*-
"""
holiday_service - 节假日服务
============================

节假日 API 获取 + 本地缓存 + 查询。
通过构造期注入 HolidayRepository，不再直接 import database。

版本: 0.8.0
"""

import json
import os
import urllib.request
from datetime import date
from pathlib import Path
from typing import List, Optional

from src.data.holiday_repo import HolidayRepository


class HolidayService:
    """节假日服务，封装 API 获取、缓存、查询。

    Args:
        api_urls:     API URL 模板列表（含 {year} 占位符）
        cache_file:   本地 JSON 缓存文件路径
        holiday_repo: HolidayRepository 实例
    """

    def __init__(
        self,
        api_urls: list,
        cache_file: str,
        holiday_repo: HolidayRepository,
    ):
        self._api_urls = api_urls
        self._cache_file = cache_file
        self._repo = holiday_repo

    def fetch(self, year: int) -> list:
        """从 API 获取指定年份的节假日数据。

        尝试顺序:
            1. API URL（主 + 备）
            2. 本地 JSON 缓存（容灾）

        获取成功后写入 DB 和本地缓存。

        Args:
            year: 年份（如 2026）

        Returns:
            节假日列表（每项含 date/name/isOffDay），空列表表示全部失败
        """
        for url_template in self._api_urls:
            url = url_template.format(year=year)
            try:
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=10, context=ctx)
                data = json.loads(resp.read())
                days = data.get("days", [])
                self._repo.save_year(year, days)
                self._save_cache(year, days)
                return days
            except Exception:
                continue

        cached = self._load_cache(year)
        if cached:
            self._repo.save_year(year, cached)
            return cached

        return []

    def ensure_loaded(self, year: int) -> list:
        """确保指定年份的节假日数据已加载到 DB。

        如果 DB 中已有该年数据 → 直接返回；
        否则 → 从 API 获取并写入 DB。

        Args:
            year: 年份

        Returns:
            节假日列表
        """
        existing = self._repo.get_all()
        if existing:
            years_in_db = set()
            for h in existing:
                y = int(h["date"][:4])
                years_in_db.add(y)
            if year in years_in_db:
                return existing

        return self.fetch(year)

    def is_holiday(self, dt: date) -> bool:
        """判断指定日期是否为放假日。"""
        h = self._repo.get(dt)
        return h is not None and h["is_off_day"] == 1

    def is_adjusted_workday(self, dt: date) -> bool:
        """判断指定日期是否为调休上班日（周末补班）。"""
        h = self._repo.get(dt)
        return h is not None and h["is_off_day"] == 0

    def get_all(self) -> list:
        """获取全部节假日缓存记录。"""
        return self._repo.get_all()

    def _save_cache(self, year: int, days: list):
        """将节假日数据保存到本地 JSON 缓存文件。"""
        Path(os.path.dirname(self._cache_file)).mkdir(parents=True, exist_ok=True)
        cache = {}
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r") as f:
                    cache = json.load(f)
            except Exception:
                cache = {}
        cache[str(year)] = days
        with open(self._cache_file, "w") as f:
            json.dump(cache, f, ensure_ascii=False)

    def _load_cache(self, year: int) -> list:
        """从本地 JSON 缓存文件读取指定年份的节假日数据。"""
        if not os.path.exists(self._cache_file):
            return []
        try:
            with open(self._cache_file, "r") as f:
                cache = json.load(f)
            return cache.get(str(year), [])
        except Exception:
            return []
