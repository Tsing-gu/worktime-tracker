"""轮询控制器并发保护测试。"""

import pytest

from src.ui.poll_controller import PollController

pytestmark = pytest.mark.gui


def test_on_tick_skips_when_previous_poll_is_running(monkeypatch) -> None:
    controller = PollController.__new__(PollController)
    controller._initialized = True
    controller._polling = True
    controller._is_busy = lambda: False

    def unexpected_start(*args, **kwargs):
        raise AssertionError("不应启动第二个轮询线程")

    monkeypatch.setattr("src.ui.poll_controller.start_managed_thread", unexpected_start)

    controller.on_tick()
