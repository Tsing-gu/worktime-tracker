# -*- coding: utf-8 -*-
"""
ui - 界面层
============

PySide6 GUI 组件，所有窗口和弹窗均在此层。
UI 层只调用 services 层，不直接操作 database / tracker / calculator。

- theme:           深色/浅色主题与 QSS 样式表
- main_window:     主窗口（今日概览 + 周/月卡片 + 功能按钮）
- settings_dialog: 设置弹窗
- calendar_dialog: 日历历史弹窗
- leave_dialog:    请假弹窗
- confirm_dialog:  次日工时确认弹窗
- update_dialog:   更新确认/进度弹窗
"""
