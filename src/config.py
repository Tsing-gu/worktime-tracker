# -*- coding: utf-8 -*-
"""
config - 全局配置常量
======================

集中管理所有配置项：数据库路径、设置键名、默认值、轮询间隔等。
所有层共享同一份配置，避免魔法字符串散落各处。

版本: 0.4.2
"""

import os

# ─── 数据库路径 ──────────────────────────────────────────────
# SQLite 数据库文件存放于用户主目录下的 .worktime_tracker/
DB_DIR = os.path.expanduser("~/.worktime_tracker")
DB_PATH = os.path.join(DB_DIR, "worktime.db")

# 节假日本地缓存文件
HOLIDAY_CACHE_FILE = os.path.join(DB_DIR, "holiday_cache.json")

# ─── 设置键名 ────────────────────────────────────────────────
# settings 表中使用的 key 常量，防止拼写不一致
SETTING_DAILY_REQUIRED_HOURS = "daily_required_hours"
SETTING_WEEKLY_WORK_DAYS = "weekly_work_days"
SETTING_OFF_THRESHOLD_MINUTES = "off_threshold_minutes"
SETTING_OFF_TIME_FLOOR = "off_time_floor"
SETTING_WORK_START_FLOOR = "work_start_floor"
SETTING_NOTIFY_ON_TARGET = "notify_on_target"
SETTING_NOTIFY_ON_OFF = "notify_on_off"
SETTING_AUTO_START = "auto_start"
SETTING_HOLIDAY_AUTO_EXCLUDE = "holiday_auto_exclude"
SETTING_AUTO_UPDATE = "auto_update"
SETTING_LAST_UPDATE_CHECK = "last_update_check"
SETTING_OFFICE_NETWORK_DOMAIN = "office_network_domain"

# ─── 默认值 ──────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    SETTING_DAILY_REQUIRED_HOURS: "8.0",
    SETTING_WEEKLY_WORK_DAYS: "5",
    SETTING_OFF_THRESHOLD_MINUTES: "60",
    SETTING_OFF_TIME_FLOOR: "19:00",
    SETTING_WORK_START_FLOOR: "06:00",
    SETTING_NOTIFY_ON_TARGET: "1",
    SETTING_NOTIFY_ON_OFF: "1",
    SETTING_AUTO_START: "0",
    SETTING_HOLIDAY_AUTO_EXCLUDE: "1",
    SETTING_AUTO_UPDATE: "0",
    SETTING_LAST_UPDATE_CHECK: "",
    SETTING_OFFICE_NETWORK_DOMAIN: "",
}

# ─── 追踪参数 ────────────────────────────────────────────────
# HID 空闲轮询间隔（毫秒）
POLL_INTERVAL_MS = 30000

# 判定为"有键鼠活动"的空闲阈值（秒），空闲 < 此值视为正在操作
ACTIVE_THRESHOLD_SECONDS = 5.0

# 判定为"用户离开"的空闲阈值（秒），空闲 > 此值视为离开
AWAY_THRESHOLD_SECONDS = 300.0

# ─── 请假类型映射 ────────────────────────────────────────────
# 内部代号 → 显示名称
LEAVE_TYPES = {
    "annual": "年假",
    "sick": "病假",
    "personal": "事假",
    "compensatory": "调休",
}

# ─── 节假日 API ──────────────────────────────────────────────
# GitHub raw 主 URL + jsDelivr CDN 备用
HOLIDAY_API_URLS = [
    "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json",
    "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json",
]

# ─── 导出文件默认路径 ────────────────────────────────────────
EXPORT_DIR = os.path.expanduser("~/Desktop")

# ─── 自动更新 ────────────────────────────────────────────────
UPDATE_CHECK_INTERVAL = 3600
UPDATE_FEED_URL = "https://raw.githubusercontent.com/Tsing-gu/worktime-tracker/main/appcast.xml"
UPDATE_FEED_FALLBACK_URL = "https://cdn.jsdelivr.net/gh/Tsing-gu/worktime-tracker@main/appcast.xml"
