# -*- coding: utf-8 -*-
"""
services - 服务编排层
======================

连接 core 业务逻辑层与 data 数据层，向上为 ui 层提供高层 API。

- worktime_service:      工时业务编排（tracker + calculator + database 协调）
- notification_service:  macOS 系统通知服务
- export_service:        CSV / Excel 数据导出
"""
