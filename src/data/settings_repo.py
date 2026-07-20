# -*- coding: utf-8 -*-
"""
settings_repo - 设置仓储
========================

操作 settings 表的键值设置读写。

版本: 0.8.0
"""

from typing import Optional

from src.data.database import Database


class SettingsRepository(Database):
    """设置表仓储，提供键值设置的读写。"""

    def get(self, key: str, default: str = "") -> str:
        """读取单个设置值。"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str):
        """写入或更新单个设置值（upsert 语义）。"""
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_all(self) -> dict:
        """读取全部设置，返回 {key: value} 字典。"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        rows = c.fetchall()
        return {row[0]: row[1] for row in rows}
