# -*- coding: utf-8 -*-
"""
worktime_repo - 每日工时仓储
============================

操作 daily_worktime 表的每日工时汇总记录。

版本: 0.8.0
"""

from datetime import datetime, date
from typing import Optional, List

from src.data.database import Database


class DailyWorktimeRepository(Database):
    """每日工时表仓储，提供上下班时间的增删改查。"""

    def get(self, work_dt: date) -> Optional[dict]:
        """获取指定日期的工时记录（原始 dict）。

        Args:
            work_dt: 工作日日期

        Returns:
            包含 daily_worktime 表一行数据的 dict，或 None
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM daily_worktime WHERE work_date = ?", (work_dt.isoformat(),))
        row = c.fetchone()
        return dict(row) if row else None

    def upsert(
        self,
        work_dt: date,
        start_time: datetime = None,
        end_time: datetime = None,
        total_hours: float = None,
        required_hours: float = None,
        leave_type: str = None,
        is_confirmed: int = None,
        has_anomaly: int = None,
        anomaly_note: str = None,
        source: str = None,
        note: str = None,
    ):
        """插入或更新每日工时记录（upsert 语义）。

        仅更新传入非 None 的字段；已存在的记录做部分更新，新记录做插入。
        """
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else None
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else None

        with self.transaction() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM daily_worktime WHERE work_date = ?", (work_dt.isoformat(),))
            existing = c.fetchone()

            if existing:
                updates = []
                params = []
                for col, val in [
                    ("start_time", start_str), ("end_time", end_str),
                    ("total_hours", total_hours), ("required_hours", required_hours),
                    ("leave_type", leave_type), ("is_confirmed", is_confirmed),
                    ("has_anomaly", has_anomaly), ("anomaly_note", anomaly_note),
                    ("source", source), ("note", note),
                ]:
                    if val is not None:
                        updates.append(f"{col} = ?")
                        params.append(val)
                if updates:
                    params.append(work_dt.isoformat())
                    c.execute(
                        f"UPDATE daily_worktime SET {', '.join(updates)} WHERE work_date = ?",
                        params,
                    )
            else:
                c.execute(
                    """INSERT INTO daily_worktime
                    (work_date, start_time, end_time, total_hours, required_hours,
                     leave_type, is_confirmed, has_anomaly, anomaly_note, source, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        work_dt.isoformat(), start_str, end_str, total_hours, required_hours,
                        leave_type, is_confirmed or 0, has_anomaly or 0, anomaly_note,
                        source or "auto", note,
                    ),
                )

    def get_range(self, start: date, end: date) -> List[dict]:
        """获取日期范围内的工时记录列表。

        Args:
            start: 起始日期（含）
            end:   结束日期（含）

        Returns:
            dict 列表，按 work_date 升序排列
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM daily_worktime WHERE work_date BETWEEN ? AND ? ORDER BY work_date ASC",
            (start.isoformat(), end.isoformat()),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]

    def delete(self, work_date_str: str):
        """删除指定日期的工时记录。

        Args:
            work_date_str: 工作日日期字符串 (YYYY-MM-DD)
        """
        with self.transaction() as conn:
            conn.execute("DELETE FROM daily_worktime WHERE work_date = ?", (work_date_str,))

    def clear_end_time(self, work_dt: date):
        """清除下班时间，恢复为"工作中"状态。

        将 end_time 和 total_hours 置 NULL，替代裸 SQL UPDATE。

        Args:
            work_dt: 工作日日期
        """
        with self.transaction() as conn:
            conn.execute(
                "UPDATE daily_worktime SET end_time = NULL, total_hours = NULL WHERE work_date = ?",
                (work_dt.isoformat(),),
            )
