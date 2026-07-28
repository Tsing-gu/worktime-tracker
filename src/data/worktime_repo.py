# -*- coding: utf-8 -*-
"""
worktime_repo - 每日工时仓储
============================

操作 daily_worktime 表的每日工时汇总记录。

版本: 0.8.0
"""

from datetime import datetime, date
from typing import Optional, List

from src.data.database import Repository, _UNSET

_DT_FORMAT = "%Y-%m-%d %H:%M:%S"


class DailyWorktimeRepository(Repository):
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
        start_time: datetime = _UNSET,
        end_time: datetime = _UNSET,
        total_hours: float = _UNSET,
        required_hours: float = _UNSET,
        leave_type: str = _UNSET,
        is_confirmed: int = _UNSET,
        has_anomaly: int = _UNSET,
        anomaly_note: str = _UNSET,
        source: str = _UNSET,
        note: str = _UNSET,
    ):
        """插入或更新每日工时记录（upsert 语义）。

        使用 _UNSET 哨兵区分"未传入"（不更新该字段）与 None/NULL（置空该字段）。
        显式传 None 会将字段置为 NULL。
        """
        start_str = start_time.strftime(_DT_FORMAT) if isinstance(start_time, datetime) else (_UNSET if start_time is _UNSET else None)

        with self.transaction() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM daily_worktime WHERE work_date = ?", (work_dt.isoformat(),))
            existing = c.fetchone()

            if existing:
                updates = []
                params = []
                for col, val in [
                    ("start_time", start_str), ("end_time", end_time),
                    ("total_hours", total_hours), ("required_hours", required_hours),
                    ("leave_type", leave_type), ("is_confirmed", is_confirmed),
                    ("has_anomaly", has_anomaly), ("anomaly_note", anomaly_note),
                    ("source", source), ("note", note),
                ]:
                    if val is not _UNSET:
                        updates.append(f"{col} = ?")
                        v = val.strftime(_DT_FORMAT) if isinstance(val, datetime) else val
                        params.append(v)
                if updates:
                    params.append(work_dt.isoformat())
                    c.execute(
                        f"UPDATE daily_worktime SET {', '.join(updates)} WHERE work_date = ?",
                        params,
                    )
            else:
                end_str = end_time.strftime(_DT_FORMAT) if isinstance(end_time, datetime) else None
                c.execute(
                    """INSERT INTO daily_worktime
                    (work_date, start_time, end_time, total_hours, required_hours,
                     leave_type, is_confirmed, has_anomaly, anomaly_note, source, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        work_dt.isoformat(),
                        start_str if start_str is not _UNSET else None,
                        end_str if end_str is not _UNSET else None,
                        total_hours if total_hours is not _UNSET else None,
                        required_hours if required_hours is not _UNSET else None,
                        leave_type if leave_type is not _UNSET else None,
                        is_confirmed if is_confirmed is not _UNSET else 0,
                        has_anomaly if has_anomaly is not _UNSET else 0,
                        anomaly_note if anomaly_note is not _UNSET else None,
                        source if source is not _UNSET else "auto",
                        note if note is not _UNSET else None,
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

    def delete(self, work_dt: date):
        """删除指定日期的工时记录。

        Args:
            work_dt: 工作日日期
        """
        with self.transaction() as conn:
            conn.execute("DELETE FROM daily_worktime WHERE work_date = ?", (work_dt.isoformat(),))

    def clear_end_time(self, work_dt: date):
        """清除下班时间，恢复为"工作中"状态。

        将 end_time 和 total_hours 置 NULL。

        Args:
            work_dt: 工作日日期
        """
        with self.transaction() as conn:
            conn.execute(
                "UPDATE daily_worktime SET end_time = NULL, total_hours = NULL WHERE work_date = ?",
                (work_dt.isoformat(),),
            )
