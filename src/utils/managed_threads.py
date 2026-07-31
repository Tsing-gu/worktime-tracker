"""应用级后台线程管理。

所有 UI 后台任务都通过这里启动，使用非 daemon 线程并在应用退出时统一等待，
避免 Python 解释器在 Qt 对象仍被线程访问时直接结束。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_threads: set[threading.Thread] = set()


def start_managed_thread(target: Callable[[], None], *, name: str) -> threading.Thread:
    """启动一个可在应用退出时统一等待的后台线程。"""

    def run() -> None:
        try:
            target()
        finally:
            with _lock:
                _threads.discard(thread)

    thread = threading.Thread(target=run, name=name, daemon=False)
    with _lock:
        _threads.add(thread)
    thread.start()
    return thread


def wait_for_managed_threads(timeout: float = 5.0) -> None:
    """在应用退出前等待登记的后台线程，超时只记录日志。"""
    deadline = time.monotonic() + timeout
    while True:
        with _lock:
            active = [thread for thread in _threads if thread.is_alive()]
        if not active:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning("仍有 %d 个后台线程未结束", len(active))
            return
        for thread in active:
            thread.join(timeout=min(remaining, 0.2))


def managed_thread_count() -> int:
    """返回当前登记的后台线程数量，供测试和诊断使用。"""
    with _lock:
        return sum(thread.is_alive() for thread in _threads)
