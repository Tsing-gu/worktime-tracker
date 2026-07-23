# -*- coding: utf-8 -*-
"""
activity_repo - 活动事件仓储
============================

操作 activity_events 表的键鼠活动记录。

版本: 0.8.0
"""

from datetime import datetime, date, timedelta
from typing import List, Optional

from src.data.database import Database
from src.core.date_utils import compute_work_date


class ActivityRepository(Database):
    """活动事件表仓储，提供键鼠活动记录的增删查。"""

    def record(self, timestamp: datetime, idle_seconds: float, is_active: bool, at_office: bool = False):
        """记录一条键鼠活动事件。

        自动根据 6:00 窗口规则计算归属工作日。

        Args:
            timestamp:    轮询时刻
            idle_seconds: HIDIdleTime（秒）
            is_active:    是否有活动（idle < 5s）
            at_office:    是否在公司内网
        """
        work_date = compute_work_date(timestamp)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO activity_events (timestamp, idle_seconds, is_active, work_date, at_office) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    idle_seconds,
                    1 if is_active else 0,
                    work_date.isoformat(),
                    1 if at_office else 0,
                ),
            )

    def cleanup(self, days: int = 14):
        """清理过期的活动记录，保留最近指定天数的数据。

        Args:
            days: 保留天数（默认 14 天）
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self.transaction() as conn:
            conn.execute("DELETE FROM activity_events WHERE timestamp < ?", (cutoff,))

    def get_today(self, work_dt: date) -> List[dict]:
        """获取指定工作日的全部活动记录。

        Args:
            work_dt: 工作日日期

        Returns:
            dict 列表，每条包含 id/timestamp/idle_seconds/is_active/work_date
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM activity_events WHERE work_date = ? ORDER BY timestamp ASC",
            (work_dt.isoformat(),),
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]

    def get_first_active_at_office(self, work_dt: date) -> Optional[datetime]:
        """获取指定工作日最早一条 active + at_office 的记录时间。

        Args:
            work_dt: 工作日日期

        Returns:
            最早的活动时间，或 None
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT timestamp FROM activity_events "
            "WHERE work_date = ? AND is_active = 1 AND at_office = 1 "
            "ORDER BY timestamp ASC LIMIT 1",
            (work_dt.isoformat(),),
        )
        row = c.fetchone()
        if row:
            return datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        return None

    def get_first_active(self, work_dt: date) -> Optional[datetime]:
        """获取指定工作日最早一条 active 的记录时间（不筛选网络）。

        Args:
            work_dt: 工作日日期

        Returns:
            最早的活动时间，或 None
        """
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT timestamp FROM activity_events "
            "WHERE work_date = ? AND is_active = 1 "
            "ORDER BY timestamp ASC LIMIT 1",
            (work_dt.isoformat(),),
        )
        row = c.fetchone()
        if row:
            return datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
        return None
