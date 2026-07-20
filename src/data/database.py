# -*- coding: utf-8 -*-
"""
database - SQLite 数据层基类
============================

提供连接管理与事务边界的基类，所有 Repository 继承此类。
数据库文件路径由 config.DB_PATH 定义。

表结构:
    - activity_events:  键鼠活动记录（每 30 秒一条）
    - daily_worktime:   每日工时汇总
    - holidays:         节假日缓存
    - settings:         键值设置

版本: 0.8.0
"""

import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

from src.config import DB_PATH, DEFAULT_SETTINGS


class Database:
    """SQLite 数据库基类，管理连接与事务边界。

    子类通过 self._conn 复用连接，多步操作用 with self.transaction() as conn 包裹。
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        self._conn: sqlite3.Connection = None

    def _get_conn(self) -> sqlite3.Connection:
        """懒加载 SQLite 连接（row_factory=Row），复用连接。"""
        if self._conn is None:
            Path(os.path.dirname(self._db_path)).mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def transaction(self):
        """事务上下文管理器：自动 commit / rollback。

        with self.transaction() as conn:
            conn.execute(...)
            conn.execute(...)
        """
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        """关闭连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def init(cls, db_path: str = DB_PATH):
        """初始化数据库：创建所有表 + 写入默认设置。

        使用 CREATE TABLE IF NOT EXISTS，可安全重复调用。
        """
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            idle_seconds REAL NOT NULL,
            is_active INTEGER NOT NULL,
            work_date DATE NOT NULL
        )""")

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

        c.execute("""CREATE TABLE IF NOT EXISTS holidays (
            date DATE PRIMARY KEY,
            name TEXT,
            is_off_day INTEGER NOT NULL
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_activity_work_date ON activity_events(work_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_events(timestamp)")

        for key, value in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

        conn.commit()
        conn.close()
