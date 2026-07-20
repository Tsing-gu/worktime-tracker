# -*- coding: utf-8 -*-
"""
database - SQLite 数据层
==========================

本模块是项目中唯一直接操作 SQLite 的模块，对上提供增删改查 API。
数据库文件路径由 config.DB_PATH 定义。

表结构:
    - activity_events:  键鼠活动记录（每 30 秒一条）
    - daily_worktime:   每日工时汇总
    - holidays:         节假日缓存
    - settings:         键值设置

版本: 0.4.2
"""

import sqlite3
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from src.config import DB_PATH, DEFAULT_SETTINGS


# ─── 连接管理 ────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """
    获取 SQLite 连接（row_factory=Row，返回类字典结果）。

    Returns:
        sqlite3.Connection 实例，调用方负责 close()
    """
    Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── 初始化 ──────────────────────────────────────────────────

def init_db():
    """
    初始化数据库：创建所有表 + 写入默认设置。

    使用 CREATE TABLE IF NOT EXISTS，可安全重复调用。
    """
    conn = get_connection()
    c = conn.cursor()

    # 键鼠活动记录表 — 每 30 秒轮询一条
    c.execute("""CREATE TABLE IF NOT EXISTS activity_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME NOT NULL,
        idle_seconds REAL NOT NULL,
        is_active INTEGER NOT NULL,
        work_date DATE NOT NULL
    )""")

    # 每日工时表 — 每天一行汇总
    c.execute("""CREATE TABLE IF NOT EXISTS daily_worktime (
        work_date DATE PRIMARY KEY,
        start_time DATETIME,
        end_time DATETIME,
        total_hours REAL,
        required_hours REAL,
        is_holiday INTEGER DEFAULT 0,
        is_adjusted_workday INTEGER DEFAULT 0,
        leave_type TEXT,
        is_confirmed INTEGER DEFAULT 0,
        has_anomaly INTEGER DEFAULT 0,
        anomaly_note TEXT,
        source TEXT DEFAULT 'auto',
        note TEXT
    )""")

    # 节假日缓存表
    c.execute("""CREATE TABLE IF NOT EXISTS holidays (
        date DATE PRIMARY KEY,
        name TEXT,
        is_off_day INTEGER NOT NULL
    )""")

    # 设置键值表
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    # 索引加速按工作日查询
    c.execute("CREATE INDEX IF NOT EXISTS idx_activity_work_date ON activity_events(work_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_events(timestamp)")

    # 写入默认设置（已存在的不覆盖）
    for key, value in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    conn.commit()
    conn.close()


# ─── 设置读写 ────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    """
    读取单个设置值。

    Args:
        key:    设置键名（建议使用 config.SETTING_* 常量）
        default: 键不存在时的默认返回值

    Returns:
        设置值字符串
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    """
    写入或更新单个设置值（upsert 语义）。

    Args:
        key:   设置键名
        value: 设置值
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    """
    读取全部设置，返回 {key: value} 字典。

    Returns:
        所有设置项的键值映射
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


# ─── 活动事件 ────────────────────────────────────────────────

def record_activity(timestamp: datetime, idle_seconds: float, is_active: bool):
    """
    记录一条键鼠活动事件。

    自动根据 6:00 窗口规则计算归属工作日。

    Args:
        timestamp:    轮询时刻
        idle_seconds: HIDIdleTime（秒）
        is_active:    是否有活动（idle < 5s）
    """
    work_date = compute_work_date(timestamp)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO activity_events (timestamp, idle_seconds, is_active, work_date) VALUES (?, ?, ?, ?)",
        (timestamp.strftime("%Y-%m-%d %H:%M:%S"), idle_seconds, 1 if is_active else 0, work_date.isoformat()),
    )
    conn.commit()
    conn.close()


def cleanup_old_activities(days: int = 14):
    """
    清理过期的活动记录，保留最近指定天数的数据。

    按时间戳删除早于 N 天前的记录，避免 activity_events 表无限膨胀。

    Args:
        days: 保留天数（默认 14 天）
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    conn.execute("DELETE FROM activity_events WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()


def compute_work_date(ts: datetime) -> date:
    """
    根据时间戳计算归属工作日。

    规则: 6:00 之前属于前一天的工作日窗口（前一天 6:00 ~ 今天 6:00）。

    Args:
        ts: 任意时刻

    Returns:
        归属工作日的 date 对象
    """
    if ts.hour < 6:
        return (ts - timedelta(days=1)).date()
    return ts.date()


def get_today_activities(work_dt: date) -> list:
    """
    获取指定工作日的全部活动记录。

    Args:
        work_dt: 工作日日期

    Returns:
        dict 列表，每条包含 id/timestamp/idle_seconds/is_active/work_date
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM activity_events WHERE work_date = ? ORDER BY timestamp ASC",
        (work_dt.isoformat(),),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 每日工时 ────────────────────────────────────────────────

def get_daily_worktime(work_dt: date) -> Optional[dict]:
    """
    获取指定日期的工时记录（原始 dict）。

    Args:
        work_dt: 工作日日期

    Returns:
        包含 daily_worktime 表一行数据的 dict，或 None
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM daily_worktime WHERE work_date = ?", (work_dt.isoformat(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_daily_worktime(
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
    """
    插入或更新每日工时记录（upsert 语义）。

    仅更新传入非 None 的字段；已存在的记录做部分更新，新记录做插入。

    Args:
        work_dt:       工作日日期
        start_time:    上班时间
        end_time:      下班时间
        total_hours:   每日工时（小时）
        required_hours: 每日工时要求
        leave_type:    请假类型 (annual/sick/personal/compensatory/none)
        is_confirmed:  是否已确认
        has_anomaly:   是否有异常
        anomaly_note:  异常说明
        source:        数据来源 'auto' | 'manual'
        note:          备注
    """
    conn = get_connection()
    c = conn.cursor()

    existing = get_daily_worktime(work_dt)
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else None
    end_str = end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else None

    if existing:
        # 部分更新：仅更新非 None 字段
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
            c.execute(f"UPDATE daily_worktime SET {', '.join(updates)} WHERE work_date = ?", params)
    else:
        # 新插入
        c.execute(
            """INSERT INTO daily_worktime
            (work_date, start_time, end_time, total_hours, required_hours, leave_type, is_confirmed, has_anomaly, anomaly_note, source, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (work_dt.isoformat(), start_str, end_str, total_hours, required_hours,
             leave_type, is_confirmed or 0, has_anomaly or 0, anomaly_note, source or "auto", note),
        )

    conn.commit()
    conn.close()


def get_date_range_worktime(start: date, end: date) -> list:
    """
    获取日期范围内的工时记录列表。

    Args:
        start: 起始日期（含）
        end:   结束日期（含）

    Returns:
        dict 列表，按 work_date 升序排列
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM daily_worktime WHERE work_date BETWEEN ? AND ? ORDER BY work_date ASC",
        (start.isoformat(), end.isoformat()),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_daily_worktime(work_date_str: str):
    """
    删除指定日期的工时记录。

    Args:
        work_date_str: 工作日日期字符串 (YYYY-MM-DD)
    """
    conn = get_connection()
    conn.execute("DELETE FROM daily_worktime WHERE work_date = ?", (work_date_str,))
    conn.commit()
    conn.close()


# ─── 节假日 ──────────────────────────────────────────────────

def save_holiday_year(year: int, holidays: list):
    """
    按年份增量写入节假日数据（只替换指定年份，不影响其他年份）。

    Args:
        year:     年份
        holidays: API 返回的节假日列表，每项含 date/name/isOffDay 字段
    """
    conn = get_connection()
    c = conn.cursor()
    # 只删除指定年份的数据，保留其他年份
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"
    c.execute("DELETE FROM holidays WHERE date >= ? AND date <= ?", (year_start, year_end))
    for h in holidays:
        # 兼容 API 字段名 isOffDay 和数据库字段名 is_off_day
        is_off = h.get("isOffDay", h.get("is_off_day", False))
        c.execute(
            "INSERT OR REPLACE INTO holidays (date, name, is_off_day) VALUES (?, ?, ?)",
            (h["date"], h["name"], 1 if is_off else 0),
        )
    conn.commit()
    conn.close()


def get_holiday(work_dt: date) -> Optional[dict]:
    """
    查询指定日期是否为节假日/调休日。

    Args:
        work_dt: 日期

    Returns:
        节假日 dict（含 date/name/is_off_day），或 None
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM holidays WHERE date = ?", (work_dt.isoformat(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_holidays() -> list:
    """
    获取全部节假日缓存记录。

    Returns:
        dict 列表，按日期升序排列
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM holidays ORDER BY date ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
