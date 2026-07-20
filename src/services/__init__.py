# -*- coding: utf-8 -*-
"""
services - 服务编排层
======================

连接 core 业务逻辑层与 data 数据层，向上为 ui 层提供高层 API。

- worktime_service:      WorktimeService 类（工时业务编排）
- export_service:        WorktimeExporter 类（CSV / Excel 导出）
- notification_service:  macOS 系统通知服务
- update_service:        UpdateService 类（纯 Python 自动更新）
"""
