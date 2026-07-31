"""
factory - 服务工厂
==================

统一创建 4 个子服务 + ExportService + UpdateService，管理依赖注入。
UI 层通过 ServiceFactory 获取各服务实例，不直接 new。

版本: 0.16.0
"""

from __future__ import annotations

import logging
from datetime import date

from src.config import DB_PATH, HOLIDAY_API_URLS, HOLIDAY_CACHE_FILE
from src.core.tracker import WorkTrackerCore
from src.data.activity_repo import ActivityRepository
from src.data.database import Repository
from src.data.holiday_repo import HolidayRepository
from src.data.settings_repo import SettingsRepository
from src.data.worktime_repo import DailyWorktimeRepository
from src.services.export_service import ExportService
from src.services.holiday_service import HolidayService
from src.services.record_service import RecordService
from src.services.settings_service import SettingsService
from src.services.stats_service import StatsService
from src.services.tracking_service import TrackingService
from src.services.update_service import UpdateService

logger = logging.getLogger(__name__)


class ServiceFactory:
    """统一创建子服务，管理依赖注入。

    使用方式:
        factory = ServiceFactory()
        factory.init_all()
        factory.tracking_service.poll_and_record()
        factory.stats_service.get_today_status()
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        """创建服务及其 Repository。

        生产环境使用默认用户数据库；测试环境传入临时路径，避免访问真实数据。
        """
        self._db_path = db_path
        # 仓储层
        self.settings_repo = SettingsRepository(db_path)
        self.activity_repo = ActivityRepository(db_path)
        self.worktime_repo = DailyWorktimeRepository(db_path)
        self.holiday_repo = HolidayRepository(db_path)

        # 节假日服务
        self.holiday_service = HolidayService(
            api_urls=HOLIDAY_API_URLS,
            cache_file=HOLIDAY_CACHE_FILE,
            holiday_repo=self.holiday_repo,
        )

        # 设置服务
        self.settings_service = SettingsService(self.settings_repo)

        # 统计服务（注册了设置变更回调）
        self.stats_service = StatsService(
            worktime_repo=self.worktime_repo,
            holiday_repo=self.holiday_repo,
            settings_service=self.settings_service,
        )

        # 记录服务
        self.record_service = RecordService(
            worktime_repo=self.worktime_repo,
            holiday_repo=self.holiday_repo,
            settings_service=self.settings_service,
            stats_service=self.stats_service,
        )

        # 追踪服务
        self.tracking_service = TrackingService(
            tracker=WorkTrackerCore(),
            activity_repo=self.activity_repo,
            worktime_repo=self.worktime_repo,
            settings_service=self.settings_service,
            holiday_service=self.holiday_service,
            record_service=self.record_service,
        )

        # 独立服务
        self.export_service = ExportService(self.worktime_repo)
        self.update_service = UpdateService(self.settings_repo)

    def init_all(self) -> None:
        """初始化全部服务（数据库 + 设置 + 节假日 + 追踪）。

        在子线程中调用（含节假日 API 网络请求），不阻塞主线程。
        """
        Repository.init(self._db_path)
        self.settings_service.init()
        self.holiday_service.ensure_loaded(date.today().year)
        self.tracking_service.init_work_date()
        logger.info("ServiceFactory 初始化完成")
