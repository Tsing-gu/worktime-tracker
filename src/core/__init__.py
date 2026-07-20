# -*- coding: utf-8 -*-
"""
core - 纯业务逻辑层
====================

本层包含工时计算器的核心业务逻辑，不直接依赖数据库或 UI 层。

- calculator:       WorktimeCalculator 类（工时统计计算）
- holiday_service:  HolidayService 类（节假日 API + 缓存）
- tracker:          WorkTracker 类（HID 空闲轮询 + 上下班判定）
- date_utils:       纯日期计算函数（跨天归属/周月范围/工作日判定）
"""
