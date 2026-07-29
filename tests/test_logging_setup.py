"""
test_logging_setup - 日志系统单元测试
======================================

覆盖 src/utils/logging_setup.py 的 setup_logging()：
- 文件 handler 写入 + 格式正确
- RotatingFileHandler 轮转（超 max_bytes 自动切分 + 保留 backup_count 份）
- stderr handler 并行输出
- 幂等性（重复调用不重复添加 handler）
- 降级（目录不可写时仅 stderr，不抛异常）

用 tmp_path fixture 隔离日志目录，不污染 ~/.worktime_tracker/logs/。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from src.utils.logging_setup import (
    DEFAULT_LOG_FILENAME,
    setup_logging,
)


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    """隔离的日志目录。"""
    d = tmp_path / "logs"
    d.mkdir()
    return d


def _read_log(log_dir: Path) -> str:
    """读取当前日志文件内容。"""
    return (log_dir / DEFAULT_LOG_FILENAME).read_text(encoding="utf-8")


class TestSetupLogging:
    """setup_logging：文件 + stderr 双 handler 初始化。"""

    def test_file_handler_writes_log(self, log_dir: Path) -> None:
        """文件 handler 正常写入日志。"""
        logger = setup_logging(level=logging.INFO, log_dir=log_dir)
        logger.info("test message")

        # flush handler 确保写入磁盘
        for h in logger.handlers:
            h.flush()

        content = _read_log(log_dir)
        assert "test message" in content
        assert "[INFO]" in content
        # 格式应包含时间、级别、模块、行号
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\]", content)

    def test_stderr_handler_attached(self, log_dir: Path) -> None:
        """stderr handler 被附加到 root logger。"""
        logger = setup_logging(level=logging.INFO, log_dir=log_dir)
        stderr_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        # 至少 1 个 StreamHandler（stderr）；RotatingFileHandler 不是 StreamHandler 子类
        assert len(stderr_handlers) >= 1

    def test_file_handler_attached(self, log_dir: Path) -> None:
        """RotatingFileHandler 被附加到 root logger。"""
        logger = setup_logging(level=logging.INFO, log_dir=log_dir)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename.endswith("app.log")

    def test_idempotent_repeated_setup(self, log_dir: Path) -> None:
        """重复调用 setup_logging 不重复添加 handler。"""
        logger1 = setup_logging(level=logging.INFO, log_dir=log_dir)
        n1 = len(logger1.handlers)

        logger2 = setup_logging(level=logging.INFO, log_dir=log_dir)
        n2 = len(logger2.handlers)

        # 同一 root logger，handler 数量不增加
        assert logger1 is logger2
        assert n1 == n2 == 2  # 1 个 file + 1 个 stderr

    def test_log_level_respected(self, log_dir: Path) -> None:
        """WARNING 级别下 DEBUG/INFO 不写入。"""
        logger = setup_logging(level=logging.WARNING, log_dir=log_dir)
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")

        for h in logger.handlers:
            h.flush()

        content = _read_log(log_dir)
        assert "warn msg" in content
        assert "debug msg" not in content
        assert "info msg" not in content

    def test_format_contains_module_and_lineno(self, log_dir: Path) -> None:
        """日志格式包含模块名和行号。"""
        from src.utils.logging_setup import get_logger

        setup_logging(level=logging.DEBUG, log_dir=log_dir)
        module_logger = get_logger("test_logging_setup")
        module_logger.debug("format test")

        for h in logging.getLogger().handlers:
            h.flush()

        content = _read_log(log_dir)
        # 格式: %(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s
        # 用 get_logger 创建的 logger 才会带模块名；root logger 的 name 是 "root"
        assert "test_logging_setup" in content
        assert re.search(r"test_logging_setup:\d+", content)

    def test_degrade_to_stderr_on_unwritable_dir(self, tmp_path: Path) -> None:
        """目录不可写时降级为仅 stderr，不抛异常。"""
        # 用一个不存在的路径 + 无权限的父目录模拟失败
        # macOS 下 /private/readonly 不让普通用户写
        bad_dir = Path("/private/readonly_nonexistent_dir/logs")

        # 不应抛异常
        logger = setup_logging(level=logging.INFO, log_dir=bad_dir)

        # 应该有 stderr handler
        stderr_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stderr_handlers) >= 1
        # 不应有 file handler
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_third_party_loggers_suppressed(self, log_dir: Path) -> None:
        """第三方库 logger (urllib3/PySide6/shiboken6) 被设置为 WARNING。"""
        setup_logging(level=logging.INFO, log_dir=log_dir)

        for name in ("urllib3", "PySide6", "shiboken6"):
            assert logging.getLogger(name).level == logging.WARNING

    def test_get_logger_returns_named_logger(self) -> None:
        """get_logger 返回带名字的 logger。"""
        from src.utils.logging_setup import get_logger

        logger = get_logger("test.module")
        assert logger.name == "test.module"


class TestRotation:
    """RotatingFileHandler 轮转行为。"""

    def test_rotation_creates_backup(self, log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """超过 max_bytes 自动轮转，旧文件改名为 .1。"""
        # 用很小的 max_bytes 触发轮转
        logger = setup_logging(level=logging.INFO, log_dir=log_dir, max_bytes=100, backup_count=2)

        # 写入超过 100 字节的内容
        for i in range(20):
            logger.info("line %02d - some content to fill the log", i)

        for h in logger.handlers:
            h.flush()

        log_file = log_dir / DEFAULT_LOG_FILENAME
        backup1 = log_dir / f"{DEFAULT_LOG_FILENAME}.1"

        # 当前日志文件应存在
        assert log_file.exists()
        # 轮转后应产生 .1 备份
        assert backup1.exists()

    def test_rotation_respects_backup_count(
        self, log_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """轮转文件数量不超过 backup_count。"""
        logger = setup_logging(level=logging.INFO, log_dir=log_dir, max_bytes=50, backup_count=2)

        # 大量写入触发多次轮转
        for i in range(100):
            logger.info("line %02d", i)

        for h in logger.handlers:
            h.flush()

        # 应该有 app.log + app.log.1 + app.log.2，但不应该有 app.log.3
        assert (log_dir / DEFAULT_LOG_FILENAME).exists()
        assert (log_dir / f"{DEFAULT_LOG_FILENAME}.1").exists()
        assert (log_dir / f"{DEFAULT_LOG_FILENAME}.2").exists()
        assert not (log_dir / f"{DEFAULT_LOG_FILENAME}.3").exists()
