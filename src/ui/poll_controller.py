"""
poll_controller - 轮询控制器
==============================

管理 30 秒定时器、子线程轮询、轮询结果分发。
从 MainWindowUI 拆分而来，只管轮询相关逻辑。

跨 controller 通信通过信号:
    - refresh_requested:          请求主窗口刷新 UI
    - resume_requested:           请求 DialogCoordinator 弹恢复确认
    - check_yesterday_requested:  请求 DialogCoordinator 弹次日确认

通过 is_busy 回调检查弹窗状态，避免轮询与弹窗冲突。

版本: 0.16.0
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6 import QtCore

from src.config import POLL_INTERVAL_MS, SETTING_NOTIFY_ON_OFF, SETTING_NOTIFY_ON_TARGET
from src.core.tracker import PollResult
from src.services import notification_service
from src.services.factory import ServiceFactory
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.services.stats_service import StatsService
from src.services.tracking_service import TrackingService
from src.utils.managed_threads import start_managed_thread

logger = logging.getLogger(__name__)


class PollController(QtCore.QObject):
    """轮询控制器：定时器 + 子线程轮询 + 结果分发。

    Args:
        parent:     父窗口（MainWindowUI）
        factory:    ServiceFactory 实例
        is_busy:    检查弹窗是否打开的回调（返回 True 时跳过轮询）
    """

    # 内部信号（子线程 → 主线程）
    poll_finished = QtCore.Signal(object)
    holiday_loaded = QtCore.Signal()

    # 跨 controller 通信信号
    refresh_requested = QtCore.Signal()
    resume_requested = QtCore.Signal()
    check_yesterday_requested = QtCore.Signal()

    def __init__(
        self,
        parent: QtCore.QObject,
        factory: ServiceFactory,
        is_busy: Callable[[], bool],
    ) -> None:
        super().__init__(parent)
        self._tracking: TrackingService = factory.tracking_service
        self._stats: StatsService = factory.stats_service
        self._record: RecordService = factory.record_service
        self._settings: SettingsService = factory.settings_service
        self._factory = factory
        self._is_busy = is_busy
        self._initialized = False

        self.poll_finished.connect(self._on_poll_finished)

        self._init_timer()
        self._on_startup()

    def _init_timer(self) -> None:
        """初始化 30 秒轮询定时器。"""
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(POLL_INTERVAL_MS)

    def _on_startup(self) -> None:
        """程序启动时调用：子线程初始化 service（含 Holiday API + 网络检测），不阻塞 UI。"""

        def worker() -> None:
            try:
                self._factory.init_all()
                self._initialized = True
                self.holiday_loaded.emit()
            except Exception:
                logger.exception("初始化失败")
                self.holiday_loaded.emit()

        start_managed_thread(worker, name="service-init")

    @QtCore.Slot()
    def on_holiday_loaded(self) -> None:
        """service.init() 完成后在主线程刷新 UI。"""
        self.refresh_requested.emit()

    def on_tick(self) -> None:
        """30 秒定时器回调。

        在子线程中执行 poll_and_record（含 ioreg/ipconfig/osascript 等阻塞 I/O），
        结果通过 poll_finished 信号回主线程处理，主线程永不阻塞。
        """
        if not self._initialized or self._is_busy():
            return

        def worker() -> None:
            try:
                result = self._tracking.poll_and_record()
                self.poll_finished.emit(result)
            except Exception as e:
                logger.warning("[Poll] 轮询失败：%s", e)
                self.poll_finished.emit(None)

        start_managed_thread(worker, name="poll")

    @QtCore.Slot(object)
    def _on_poll_finished(self, result: PollResult | None) -> None:
        """轮询完成后在主线程处理结果：通知/弹窗/refresh_ui。"""
        if result is None:
            self.refresh_requested.emit()
            return

        # ── 下班通知（子线程发送 osascript，不阻塞主线程）──
        if result.event == "off" and result.off_time is not None:
            if self._get_setting_bool(SETTING_NOTIFY_ON_OFF, True):
                off_time = result.off_time
                start_managed_thread(
                    lambda: notification_service.notify_off_work(
                        off_time.strftime("%H:%M"), result.worked_hours
                    ),
                    name="off-work-notification",
                )
        # ── 达标通知 ──
        elif result.event == "target_reached":
            if self._get_setting_bool(SETTING_NOTIFY_ON_TARGET, True):
                status = self._stats.get_today_status()
                required = status.required_hours
                start_managed_thread(
                    lambda: notification_service.notify_target_reached(
                        result.worked_hours, required
                    ),
                    name="target-notification",
                )
        # ── 下班后回来 → 弹窗确认恢复 ──
        elif result.event == "back" and not self._is_busy():
            self.resume_requested.emit()

        # ── 先刷新 UI（含日期），确保跨天后界面立即更新 ──
        self.refresh_requested.emit()

        # ── 再弹次日确认（放最后）──
        if not self._is_busy() and self._record.should_check_yesterday():
            self.check_yesterday_requested.emit()

    def stop(self) -> None:
        """停止定时器（退出时调用）。"""
        self.timer.stop()

    # ─── 辅助方法 ──────────────────────────────────────────

    def _get_setting_bool(self, key: str, default: bool = False) -> bool:
        """读取布尔型设置值。"""
        return self._settings.get_setting(key, "1" if default else "0") == "1"
