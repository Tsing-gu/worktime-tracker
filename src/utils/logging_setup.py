"""
logging_setup - 日志系统初始化
================================

统一配置标准库 logging：RotatingFileHandler 写入文件 + StreamHandler 输出到 stderr。
主进程入口（main.py）调用 setup_logging() 一次完成初始化，后续各模块用
`logging.getLogger(__name__)` 获取 logger 即可，无需关心 handler 配置。

日志文件路径：~/.worktime_tracker/logs/app.log
轮转策略：单文件 10MB，最多保留 5 份（共 50MB）
日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL

线程安全：logging 模块本身线程安全，子线程直接用 getLogger 即可。

版本: 0.16.0
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

# ─── 常量 ──────────────────────────────────────────────────────

# 日志目录（与数据库同目录，~/.worktime_tracker/logs/）
DEFAULT_LOG_DIR: Final[Path] = Path.home() / ".worktime_tracker" / "logs"

# 日志文件名
DEFAULT_LOG_FILENAME: Final[str] = "app.log"

# 单文件最大字节数（10MB）
DEFAULT_MAX_BYTES: Final[int] = 10 * 1024 * 1024

# 保留的轮转文件份数（5 份 × 10MB = 最多 50MB）
DEFAULT_BACKUP_COUNT: Final[int] = 5

# 日志格式
DEFAULT_LOG_FORMAT: Final[str] = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"

DEFAULT_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_dir: Path | str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """初始化全局日志配置。

    在程序入口（main.py）调用一次，配置 root logger：
    - RotatingFileHandler：写入 log_dir/app.log，按 max_bytes 轮转，保留 backup_count 份
    - StreamHandler：输出到 stderr（开发环境实时查看）

    幂等性：重复调用不会重复添加 handler（先清理已有 handler）。

    Args:
        level:         日志级别（默认 INFO）
        log_dir:       日志目录（默认 ~/.worktime_tracker/logs/）
        max_bytes:     单文件最大字节数（默认 10MB）
        backup_count:  轮转保留份数（默认 5）

    Returns:
        配置好的 root logger

    Note:
        初始化失败（如目录不可写）时降级为仅 stderr，不抛异常，
        确保日志系统初始化不会导致主进程崩溃。
    """
    # 解析日志目录
    if log_dir is None:
        log_dir = DEFAULT_LOG_DIR
    log_dir_path = Path(log_dir)

    # 配置 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清理已有 handler（保证幂等）
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 日志格式
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT)

    # ── 文件 handler（轮转）──
    file_handler: logging.Handler | None = None
    try:
        log_dir_path.mkdir(parents=True, exist_ok=True)
        log_file = log_dir_path / DEFAULT_LOG_FILENAME
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        # 目录创建失败或文件不可写 → 降级为仅 stderr，不阻塞启动
        root_logger.addHandler(_make_stderr_handler(level, formatter))
        root_logger.warning("日志文件初始化失败，降级为仅 stderr 输出：%s", e)
        return root_logger

    # ── stderr handler（开发环境实时查看）──
    stderr_handler = _make_stderr_handler(level, formatter)
    root_logger.addHandler(stderr_handler)

    # ── 减少第三方库的日志噪音 ──
    for noisy in ("urllib3", "PySide6", "shiboken6"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root_logger.info("日志系统初始化完成，日志文件：%s", log_dir_path / DEFAULT_LOG_FILENAME)
    return root_logger


def _make_stderr_handler(level: int, formatter: logging.Formatter) -> logging.Handler:
    """创建 stderr handler。"""
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(formatter)
    return stderr_handler


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger 的便捷函数。

    各模块顶部用 `logger = get_logger(__name__)` 获取 logger，
    日志会自动带上模块名（如 src.core.tracker）。

    Args:
        name: 模块名（通常传 __name__）

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)
