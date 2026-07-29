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

版本: 0.16.0
"""

import logging
import os
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.config import DB_PATH, DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

# datetime 存入 SQLite 的统一格式串
DT_FORMAT = "%Y-%m-%d %H:%M:%S"

# 哨兵：区分"未传入参数"（不更新字段）与 None（置 NULL）
_UNSET = object()


class Repository:
    """SQLite 数据库基类，管理连接与事务边界。

    子类通过 self._conn 复用连接，多步操作用 with self.transaction() as conn 包裹。
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        """懒加载 SQLite 连接（row_factory=Row），复用连接。

        check_same_thread=False 允许子线程使用同一连接，
        配合 WAL 模式实现多读 + 一写的并发安全。
        使用 threading.Lock 保证懒加载的线程安全。
        """
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    Path(os.path.dirname(self._db_path)).mkdir(parents=True, exist_ok=True)
                    self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
                    self._conn.row_factory = sqlite3.Row
                    self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """事务上下文管理器：自动 commit / rollback。

        使用 threading.Lock 保证写事务的串行化，避免多线程并发写冲突。

        with self.transaction() as conn:
            conn.execute(...)
            conn.execute(...)
        """
        conn = self._get_conn()
        with self._lock:
            try:
                yield conn
                conn.commit()
            except Exception:
                logger.exception("事务回滚")
                conn.rollback()
                raise

    def close(self) -> None:
        """关闭连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def init(cls, db_path: str = DB_PATH) -> None:
        """初始化数据库：创建所有表 + 写入默认设置。

        使用 CREATE TABLE IF NOT EXISTS，可安全重复调用。
        """
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(
            """CREATE TABLE IF NOT EXISTS activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            idle_seconds REAL NOT NULL,
            is_active INTEGER NOT NULL,
            work_date DATE NOT NULL,
            at_office INTEGER DEFAULT 0
        )"""
        )

        c.execute(
            """CREATE TABLE IF NOT EXISTS daily_worktime (
            work_date DATE PRIMARY KEY,
            start_time DATETIME,
            end_time DATETIME,
            total_hours REAL,
            required_hours REAL,
            leave_type TEXT,
            is_confirmed INTEGER DEFAULT 0,
            has_anomaly INTEGER DEFAULT 0,
            anomaly_note TEXT,
            source TEXT DEFAULT 'auto',
            note TEXT
        )"""
        )

        c.execute(
            """CREATE TABLE IF NOT EXISTS holidays (
            date DATE PRIMARY KEY,
            name TEXT,
            is_off_day INTEGER NOT NULL
        )"""
        )

        c.execute(
            """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
        )

        c.execute("CREATE INDEX IF NOT EXISTS idx_activity_work_date ON activity_events(work_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_events(timestamp)")

        # ── migration: 老库表结构补列（新库已含完整列，跳过）──
        _ensure_column(c, "activity_events", "at_office", "INTEGER DEFAULT 0")

        for key, value in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

        conn.commit()
        conn.close()
        logger.info("数据库初始化完成：%s", db_path)


def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    """检查表是否有指定列，没有则 ALTER TABLE ADD COLUMN。

    用于老库迁移，新库 CREATE TABLE 已含完整列不会触发。
    """
    cursor.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if column not in existing_cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
