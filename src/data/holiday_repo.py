# -*- coding: utf-8 -*-
"""
holiday_repo - 节假日仓储
========================

操作 holidays 表的节假日缓存记录。

版本: 0.8.0
"""

from datetime import date
from typing import Optional, List

from src.data.database import Database


class HolidayRepository(Database):
    """节假日表仓储，提供节假日缓存的读写。"""

    def save_year(self, year: int, holidays: list):
        """按年份增量写入节假日数据（只替换指定年份，不影响其他年份）。

        Args:
            year:     年份
            holidays: API 返回的节假日列表，每项含 date/name/isOffDay 字段
        """
        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM holidays WHERE date >= ? AND date <= ?",
                (year_start, year_end),
            )
            for h in holidays:
                is_off = h.get("isOffDay", h.get("is_off_day", False))
                conn.execute(
                    "INSERT OR REPLACE INTO holidays (date, name, is_off_day) VALUES (?, ?, ?)",
                    (h["date"], h["name"], 1 if is_off else 0),
                )

    def get(self, work_dt: date) -> Optional[dict]:
        """查询指定日期是否为节假日/调休日。

        Args:
            work_dt: 日期

        Returns:
            节假日 dict（含 date/name/is_off_day），或 None
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM holidays WHERE date = ?", (work_dt.isoformat(),))
        row = c.fetchone()
        return dict(row) if row else None

    def get_all(self) -> List[dict]:
        """获取全部节假日缓存记录。

        Returns:
            dict 列表，按日期升序排列
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM holidays ORDER BY date ASC")
        rows = c.fetchall()
        return [dict(r) for r in rows]
