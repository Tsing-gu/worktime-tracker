## [0.10.0] - 2026-07-23

- **变更**: 上班判定改为从 activity_events 底表查最早活跃记录回推，替代实时 HID 回推：开启只记录在公司时间时查 active+at_office，关闭时查所有 active

## [0.9.0] - 2026-07-23

- **变更**: pmset 回溯从自动上班判定中移除，改为手动功能：修改上班时间弹窗新增「从 pmset 读取」按钮，用户可选择手动输入或自动读取

## [0.8.9] - 2026-07-23

- **修复**: pmset 回溯补录不受网络验证影响：allow_hid_start 只控制优先级 5（HID 回推），优先级 4（pmset 回溯）始终只看时间

## [0.8.8] - 2026-07-23

- **新增**: 新增「只记录在公司时间」设置项：开启后上班判定需同时满足 HID 活动 + 公司网络，关闭则仅判断时间

## [0.8.7] - 2026-07-23

- **新增**: 每天早上确认工时后自动检查更新，有新版则弹更新确认窗

## [0.8.6] - 2026-07-23

- **修复**: 修复部分用户 SSL 证书验证失败导致无法检查更新：_fetch_feed 跳过 SSL 证书验证

## [0.8.5] - 2026-07-23

- **修复**: 修复检查更新时网络失败被误报为「已是最新版本」：拉取 appcast 失败现在抛 RuntimeError，UI 显示「检查失败」而非「已是最新」

## [0.8.4] - 2026-07-23

- **修复**: 修复睡眠跨天场景下班时间未记录：reset_for_new_day 抢在下班检测之前执行，导致前一天 end_time 永远为 NULL。新增 _backfill_off_time 在跨天重置前用 now-idle 补录下班时间

## [0.8.3] - 2026-07-23

- **新增**: 公司网络交叉验证：每 30 秒轮询时检测 DHCP domain_search，at_office 写入 activity_events 底表；设置弹窗新增「记录办公网络」按钮，点击检测当前网络域名存入 settings（office_network_domain），参数化公司内网名

## [0.8.2] - 2026-07-21

- **修复**: 修复跨天后主页日期不自动刷新：date_label 仅在 __init__ 设置一次，refresh_ui 未更新，导致跨天后日期滞后一天直到重启软件
- **修复**: 弹窗与手动下班解耦：移除 check_yesterday 中 is_confirmed==1 的跳过逻辑，无论手动/自动下班，次日早上均弹窗确认下班时间

## [0.8.1] - 2026-07-21

- **修复**: 重构引入的工作日判定回归 bug：`is_workday`/`is_rest_day`/`get_period_range`/`get_previous_workday` 调用时误传 `holiday_auto_exclude`(bool) 作为 `weekly_work_days`(int) 参数，导致只有周一判定为工作日，总工作天数严重偏少
- **修复**: 所有查询当日日期的请求统一使用 `compute_work_date(now)`（6:00 跨天归属），不再用 `date.today()`，修复凌晨时段上一个工作日判定错误（如凌晨1点应归属前一天，上一个工作日应为上周五而非当天）

## [0.8.0] - 2026-07-20

- **重构**: 全面 OOP 重构，所有散装模块级函数改为类封装
  - data 层: Database 基类 + 4 Repository（Settings/Activity/DailyWorktime/Holiday），事务边界
  - core 层: WorktimeCalculator 类（消除 get_period_stats/get_month_stats 100+ 行重复）
  - core 层: HolidayService 类（构造期注入 HolidayRepository，不再直接 import database）
  - core 层: WorkTracker 状态私有化 + is_started/is_off 查询方法
  - core 层: date_utils 从 database 迁出纯日期函数
  - services 层: WorktimeService 注入 Repository+Calculator，消除裸 SQL，补齐 get_settings/update_settings
  - services 层: WorktimeExporter 类（消除 CSV/Excel 字段提取重复）
  - services 层: UpdateService 注入 SettingsRepository，静态方法下沉到 utils
  - ui 层: 删除所有直接 import database（6 处改走 service）
  - ui 层: ConfirmYesterdayDialog 改为参数传入数据
  - utils 层: 新增 paths/text/net 工具文件
- **新增**: ARCHITECTURE.md 架构与调用关系文档
- **新增**: CLAUDE.md + docs/CODING_RULES.md 编码规则（强制 OOP + 分层 + 同步更新）

## [0.7.3] - 2026-07-20

- **修复**: 主页面进度条不显示：内联样式只设 chunk 遮蔽了全局 track 底色，现统一设置 track+chunk
- **重构**: `_style_progress_bar` 改为实例方法，调用方只传 worked/required，百分比/钳制/变绿逻辑集中到一处
- **修复**: 工时超过目标时进度条不变绿（如 11.8h/11.5h）

## [0.7.2] - 2026-07-20

- **修复**: 窗口隐藏到托盘后，点击 macOS dock 图标无法重新展开主窗口：新增应用激活事件过滤器，被激活且主窗口不可见时调用 show_normal 恢复

## [0.7.1] - 2026-07-20

- **修复**: 下载更新时跨线程操作 Qt 控件导致崩溃：progress 回调改为 QMetaObject.invokeMethod 主线程更新

## [0.7.0] - 2026-07-20

- **变更**: 删除自动更新检测，仅用户手动点击检查更新时才生效

## [0.6.6] - 2026-07-20

- **新增**: 下载进度弹窗新增取消下载按钮，关闭弹窗也自动取消

## [0.6.5] - 2026-07-20

- **修复**: 修复打包后路径问题：资源文件路径用 sys._MEIPASS，spec 打包 resources/ 和 CHANGELOG.md

## [0.6.4] - 2026-07-20

- **修复**: 打包后版本号读取错误：优先从 _MEIPASS/Resources 读 VERSION，不再受项目目录影响

## [0.6.4] - 2026-07-20

- **修复**: QCheckBox 完全使用 Qt 原生样式，修复勾选失效问题

## [0.6.3] - 2026-07-20

- **修复**: 自动更新下载完成后未退出主进程导致安装失败

## [0.6.2] - 2026-07-20

- **修复**: QCheckBox 选中状态用 Qt 原生勾选标记，不再填满色

## [0.6.1] - 2026-07-20

- **新增**: 设置应用图标 + 设置弹窗加版本号显示

## [0.6.0] - 2026-07-20

- **新增**: 纯 Python 自动更新（方案 B）：启动 + 每小时检查，首次用户确认后自动下载安装重启
- **新增**: 托盘菜单「检查更新」手动触发
- **新增**: appcast.xml 版本清单（GitHub Releases 托管 DMG，jsDelivr 备用）

## [0.5.2] - 2026-07-18

- **修复**: 凌晨时段（0:00~6:00）主页面和菜单栏时长卡未正常显示上班时长和进度：get_today_status/get_period_stats/get_month_stats 误用 date.today()，改为 compute_work_date(datetime.now()) 与跨天 6:00 规则一致
- **新增**: 菜单栏时长卡新增「预计下班 HH:MM」（当前时间 + 剩余工时），已下班时不显示
- **修复**: 菜单栏右键「打开主界面」在窗口最小化时点击无效：show_normal 改为判断最小化/未显示时调用 showNormal() 恢复
- **新增**: 所有进度条（今日/菜单栏弹窗/本期/本月）达到 100% 时变绿色

## [0.5.1] - 2026-07-16

- **修复**: 本期/本月概览 line3：剩余天数含当天，每天需达标不计当天工时，最后一天文案改为「今天干完就放假啦！还剩xx.xh」

## [0.5.0] - 2026-07-16

- **变更**: 本周概览改为本期概览（以连续非工作日分段），本月概览改为工作日口径，请假天从分母扣除

## [0.4.7] - 2026-07-15

- **修复**: 统一 required_hours 写入与读取：上班时写入 DB，所有界面统一从 DB 读取，改设置后更新当天记录

## [0.4.6] - 2026-07-15

- **修复**: 修复周月统计未下班天数工时不计入问题

## [0.4.5] - 2026-07-15

- **修复**: 修复凌晨加班下班时间无法自动记录（0:00~6:00 时段豁免下班时间下限）

## [0.4.4] - 2026-07-15

- **修复**: 数据表修复: 1)holidays按年份增量写入不再跨年丢失 2)required_hours持久化到daily_worktime防止改设置后历史达标状态变化 3)删除未使用的week_start_day设置

## [0.4.3] - 2026-07-15

- **新增**: activity_events 表保留 14 天，每天首次轮询时自动清理过期记录

## [0.4.2] - 2026-07-15

- **修复**: 版本号格式改为 0.x.xx（正式版前 MAJOR 固定为 0）

# CHANGELOG - 工时计算器变更记录

本文件由 `src/utils/version.py` 自动维护，记录每次版本变更。

---

## [0.4.1] - 2026-07-15

- **修复**: 修复上下班判定6个问题: 1)统一上班逻辑避免覆盖 2)下班后回来弹窗确认恢复计时 3)pmset日志缺失静默等待 4)下班时间下限完整时分比较

## [0.4.0] - 2026-07-15

- **移除**: 清理根目录下重构后废弃的旧文件: calculator.py/database.py/exporter.py/holiday.py/notifier.py/tracker.py/__pycache__/build/dist/工时计算器.spec

## [0.3.3] - 2026-07-15

- **修复**: 去掉 setContextMenu，左键只弹时长卡，右键弹功能菜单，不再同时出现两个

## [0.3.2] - 2026-07-15

- **修复**: 托盘图标弹窗改用非阻塞 popup() 替代 exec_()，彻底修复快速多次点击导致应用卡死

## [0.3.1] - 2026-07-15

- **修复**: 修复托盘图标快速多次点击导致菜单叠加卡死的问题

## [0.3.0] - 2026-07-15

- **变更**: 项目架构重构 — 从单层目录平铺改为 src/ 分层架构（core/data/services/ui/utils）
- **变更**: 全部源文件添加详细注释（文件头、类 docstring、函数 docstring、关键逻辑行内注释）
- **变更**: core 层完全脱离数据库 — calculator 改为纯函数接收参数，tracker 不直接写 DB，通过 services.worktime_service 编排
- **新增**: 版本管理机制 — VERSION 文件 + CHANGELOG.md + utils/version.py 工具函数（record_change 自动 bump 版本）
- **变更**: main.py 从 1353 行精简为纯入口文件（~50 行），GUI 逻辑拆分到 ui/ 下 6 个独立模块
- **变更**: 系统调用封装到 utils/system.py — ioreg/pmset/osascript 统一收口
- **新增**: config.py 集中管理所有配置常量、设置键名、默认值，消除魔法字符串
- **新增**: data/models.py 定义数据模型 dataclass（WorkTimeRecord/ActivityEvent/Holiday 等）

## [0.2.0] - 2026-07-15

- **新增**: 初版工时计算器功能实现 — 键鼠追踪、上下班判定、周/月统计、日历、请假、导出、托盘驻留、开机自启

---
