"""应用运行时线程管理测试。"""

import threading

from src.app.runtime import (
    managed_thread_count,
    start_managed_thread,
    wait_for_managed_threads,
)


def test_managed_thread_is_waited_and_removed() -> None:
    finished = threading.Event()

    start_managed_thread(finished.set, name="test-managed-thread")
    wait_for_managed_threads(timeout=1)

    assert finished.is_set()
    assert managed_thread_count() == 0


def test_managed_thread_exception_does_not_escape() -> None:
    def failing_worker() -> None:
        raise RuntimeError("expected test failure")

    start_managed_thread(failing_worker, name="test-failing-thread")
    wait_for_managed_threads(timeout=1)

    assert managed_thread_count() == 0
