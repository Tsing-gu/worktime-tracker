"""应用运行时资源管理。"""

from src.app.runtime.thread_manager import (
    managed_thread_count,
    start_managed_thread,
    wait_for_managed_threads,
)

__all__ = [
    "managed_thread_count",
    "start_managed_thread",
    "wait_for_managed_threads",
]
