## [0.15.2] - 2026-07-28

- **修复**: 修复概览卡片"日均工时"在今天请假时显示为 0 的问题
- **修复**: 修复跨年时下一年节假日不自动获取的问题
- **修复**: 修复更新下载网络超时时无限重试的问题
- **修复**: 修复自动更新安装脚本中途失败不退出的问题
- **变更**: 优化日历页面的加载速度
- **变更**: 优化主界面统计卡片的刷新性能

## [0.15.1] - 2026-07-28

- **修复**: 修复系统通知中包含双引号时通知发送失败的问题
- **修复**: 修复连接公司内网含多个域名时"只记录在公司时间"功能误判的问题
- **修复**: 修复导出文件名含中文时部分情况下编码错误的问题
- **修复**: 修复清除下班记录后无法重新记录下班的问题
- **修复**: 修复多线程同时写入数据库时可能崩溃的问题
- **修复**: 修复删除历史记录时日期格式不一致的问题

## [0.15.0] - 2026-07-27

- **变更**: 重构命名统一层后缀：services层统一Service后缀(WorktimeExporter→ExportService)，core层统一Core后缀(WorkTracker→WorkTrackerCore, WorktimeCalculator→WorktimeCalculatorCore)，data层基类Database→Repository，ui层10个类统一加UI后缀；文件归属整理：holiday_service从core移到services(业务编排)，date_utils从core移到utils(纯函数工具)

## [0.14.5] - 2026-07-27

- **修复**: 消除所有主线程卡顿点：settings_dialog/edit_start_dialog/calendar_dialog 残留 QMessageBox 静态方法(隐式 exec_)改非模态 show()；_on_record_office subprocess(ipconfig timeout=3)移入 worker 线程；_find_holiday 线性扫描 O(N) 改 dict O(1) 查找；get_period_range 重复调用消除(service+calculator 各调一次)；_iterate_range records 线性查找改 dict 索引；refresh_ui 统计计算从 O(N²) 降至 0.2ms

## [0.14.4] - 2026-07-27

- **修复**: 修复修改上班弹窗「从 pmset 读取」按钮卡在读取中：Q_ARG(object, datetime) 在 PySide6 QueuedConnection 下找不到 QMetaType 致 worker 线程静默崩溃，改为 Q_ARG(str) 传时间字符串

## [0.14.3] - 2026-07-27

- **修复**: 修复自动检查更新与次日确认弹窗状态冲突：非模态化后两者并发导致 _pending_dialog 引用覆盖/_busy 状态混乱；_check_update_after_confirm 移到次日确认弹窗 on_finished 回调里，用户确认后才触发自动检查；_show_update_confirm 加 _busy 守卫

## [0.14.2] - 2026-07-27

- **修复**: 修复周末长跑崩溃(Too many nested CFRunLoopRuns)：所有主线程弹窗改为非模态 show()+finished 信号驱动，彻底消除嵌套事件循环；新增 _busy 守卫，弹窗未关闭时定时器 tick 静默丢弃本轮，防止事件积压累积嵌套层级；UpdateProgressDialog 去除 setModal(True)；日历右键菜单 QMenu.exec_() 改为 popup()，子弹窗级联非模态化

## [0.14.1] - 2026-07-24

- **修复**: 修复 QMessageBox 标准按钮需点两次：统一封装 _msg_box helper 禁用 autoDefault + NoFocus

## [0.14.0] - 2026-07-24

- **新增**: 主线程阻塞全面解耦：轮询/更新检查/通知/pmset/Holiday API/Excel导出全部子线程化，主线程永不阻塞
- **修复**: ioreg 加 timeout=5 兜底防止子线程永久卡死
- **修复**: 修复取消更新后弹窗不关闭：下载 urlopen timeout 从 300s 降至 10s，resp.read 超时后检查取消标志而非卡死
- **修复**: 修复修改上班弹窗确认按钮卡住：on_tick 定时器在模态对话框打开时跳过轮询，避免 subprocess 阻塞主线程

## [0.13.7] - 2026-07-24

- **修复**: 修复设置/请假/确认弹窗输入框无法点击聚焦 — NoFocus 改为 ClickFocus

## [0.13.6] - 2026-07-24

- **修复**: 修复重启后重复触发昨日工时确认弹窗 — check_yesterday 改为只返回 is_confirmed=0 的记录

## [0.13.5] - 2026-07-24

- **修复**: 修复日历日期格 hover 无效果：set_status 本地样式表覆盖了 app 级 QSS 的 :hover 规则，改为在本地样式表中显式写入 :hover 规则；补充 WA_Hover 属性；"今天"边框标记从字符串拼接改为 set_status 的 is_today 参数

## [0.13.4] - 2026-07-24

- **修复**: 修复对话框按钮需点两次才生效：所有 QDialogButtonBox 按钮统一设 NoFocus + setAutoDefault(False)，消除 macOS autoDefault 首次点击只获取焦点的行为
- **修复**: 修复按钮点击后失去 hover/click 效果：theme.py 为 #PrimaryBtn/#SecondaryBtn/#DangerBtn 补充 :focus 样式（与 :hover 一致）
- **修复**: 删除 settings_dialog 中重复创建的孤儿 QDialogButtonBox

## [0.13.3] - 2026-07-24

- **修复**: 修复次日确认弹窗和自动更新检查被锁死不弹：check_yesterday 不再内部置位，跨天时重置 _checked_yesterday，统一用 service.should_check_yesterday() 替代 UI 层 checked_yesterday 标志
- **修复**: 修复跨天后主页日期被次日确认弹窗阻塞不刷新：refresh_ui 移到弹窗调用之前

## [0.13.2] - 2026-07-24

- **修复**: 修复跨天后主页日期被次日确认弹窗阻塞不刷新：调整 on_tick 执行顺序，refresh_ui 移到弹窗调用之前，确保跨天后日期立即更新

## [0.13.1] - 2026-07-23

- **变更**: UI细节优化：导出仅保留Excel格式+取消按钮置左；日历页面美化(格子增大+配色重设计+固定宽度Card居中+图例色块)；主窗口状态行合并为单Card(按钮行+信息行)；预计下班替换今日目标；深浅色实时切换(ThemeManager信号机制)；按钮hover/focus样式统一消除闪烁；输入控件NoFocus/ClickFocus消除自动聚焦；请假类型下拉框显示中文

## [0.13.0] - 2026-07-23

- **变更**: UI整体改造：消除内联样式统一用objectName+QSS管理；修复硬编码颜色；主窗口状态行垂直居中重排；设置弹窗QGroupBox分组；导出格式改自定义按钮；修改上班时间对话框抽取为独立文件

## [0.12.0] - 2026-07-23

- **变更**: 下班判定纳入网络条件：开启「只记录在公司时间」时，离开公司网络或HID空闲超阈值任一满足即判下班；跨天补录也查最后一条at_office记录

## [0.11.0] - 2026-07-23

- **变更**: 全部UI按钮和选项中文化：加载Qt内置中文翻译使标准按钮(OK/Cancel/Yes/No)显示中文；请假类型下拉框改显示中文名(年假/病假/事假/调休)；导出弹窗文案中文化；修改上班时间/设置/日历补录弹窗按钮显式设为中文

## [0.10.3] - 2026-07-23

- **修复**: 修复 v0.10.2 无法启动：init 方法调用 get_network_status 未在模块顶部 import

## [0.10.2] - 2026-07-23

- **修复**: 修复取消下载后弹窗卡住不关闭：worker 线程检测到取消后调用 close() 关闭对话框

## [0.10.1] - 2026-07-23

- **修复**: 修复下载 DMG 时 SSL 证书验证失败：download_update 跳过 SSL 验证
- **修复**: 修复获取节假日时 SSL 证书验证失败：holiday_service 也跳过 SSL 验证

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
