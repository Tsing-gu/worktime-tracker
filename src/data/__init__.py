# -*- coding: utf-8 -*-
"""
data - 数据层
==============

本层是唯一直接操作 SQLite 数据库的层。

- database:       Database 基类（连接管理 + 事务边界）
- settings_repo:  SettingsRepository（settings 表）
- activity_repo:  ActivityRepository（activity_events 表）
- worktime_repo:  DailyWorktimeRepository（daily_worktime 表）
- holiday_repo:   HolidayRepository（holidays 表）
- models:         数据模型 dataclass
"""
