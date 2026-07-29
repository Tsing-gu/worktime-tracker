"""
services - 服务编排层
======================

连接 core 业务逻辑层与 data 数据层，向上为 ui 层提供高层 API。

通过 ServiceFactory 统一创建和获取各子服务:

- factory:               ServiceFactory（统一创建 + 依赖注入）
- tracking_service:      TrackingService（轮询追踪 / 上下班判定）
- stats_service:         StatsService（今日 / 本期 / 本月统计）
- record_service:        RecordService（请假 / 补录 / 清除 / 次日确认）
- settings_service:      SettingsService（类型化设置读写 + 迁移）
- export_service:        ExportService（CSV / Excel 导出）
- notification_service:  macOS 系统通知服务
- update_service:        UpdateService（纯 Python 自动更新）
- holiday_service:       HolidayService（节假日缓存 + API）

版本: 0.16.0
"""
