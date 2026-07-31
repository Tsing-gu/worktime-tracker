# 开发准则

## 架构边界

项目采用单向分层：`UI → Services → Core`，`Services → Data/Core`，`Data` 不依赖 UI。
`config`、`data.models` 和无状态 `utils` 是共享基础模块，但不得借此绕过分层。

| 层 | 允许负责 | 禁止负责 |
| --- | --- | --- |
| `src/ui/` | 窗口、对话框、Qt 信号槽、展示状态 | 直接操作 SQLite、网络、系统命令、业务计算 |
| `src/services/` | 用例编排、线程边界、依赖注入、外部服务协调 | 把 UI 控件传入业务层；绕过 Repository 写数据库 |
| `src/core/` | 可参数化测试的状态机、工时计算和领域规则 | Repository、SQLite、网络、文件和系统调用 |
| `src/data/` | Repository、SQLite schema、事务、数据模型转换 | UI 逻辑、网络请求、业务流程 |
| `src/utils/` | 无状态通用工具（日期、路径、系统适配） | 持有业务状态或编排跨层流程 |
| `src/app/` | 应用装配、运行时线程管理、退出生命周期 | 业务规则、UI 控件和数据库操作 |

Core 可以引用共享的 `data.models` 和数据库时间格式常量，但不得创建 Repository 或连接 SQLite。
UI 可以展示 Service 返回的领域模型，也可以引用共享配置和模型，但不得直接依赖具体 Repository。
新增依赖必须遵循这个方向，禁止循环导入和跨层偷渡。

UI 内部按职责拆分为 `views/`、`components/`、`controllers/`、`models/` 和后续的
`animations/`。`views/` 负责页面组合，`components/` 负责可复用控件，
`controllers/` 将 Service 结果转换为展示状态，`models/` 保存展示状态，动画只处理视觉效果。
UI 实现必须放在对应子包中，禁止重新在 `src/ui/` 根目录新增窗口、控制器或主题实现。
线程管理属于 `src/app/runtime/`，不得重新放回 `src/utils/` 或由单个窗口私自维护。

### 依赖注入与状态

- Service 的外部依赖在构造期注入，便于测试替换 Repository、网络客户端和系统适配器。
- Core 不保存数据库状态；每次计算所需的记录、配置和当前时间显式传入。
- UI 只保存展示状态和窗口生命周期；跨线程结果通过 signal/slot 回到主线程。
- 业务层不新增隐式全局单例；UI 生命周期管理器如确需单例，必须有明确的生命周期、可测试的重置方式，并避免承载业务状态。

## 可靠性规则

- 主线程不得执行网络、`subprocess`、长时间数据库操作或文件导出；通过 Qt worker/signal 解耦。
- 系统调用必须设置超时，并覆盖调用失败、权限不足和返回值异常。
- 数据库多步写操作使用事务；测试不得污染 `~/.worktime_tracker`。
- 日期、时区和跨天逻辑必须使用显式固定时间测试，禁止依赖测试运行时的当前时间。
- 用户输入在 UI 边界校验，Service 仍需做必要的业务校验。
- 后台线程不得直接操作 Qt 控件；线程退出、取消和异常必须有明确的 signal/回调路径。
- 网络请求必须设置连接/读取超时，不得无限重试；取消操作必须能结束 worker 和 UI 状态。
- SQLite 连接的生命周期由 Repository 管理，跨线程访问必须显式考虑锁、事务和连接策略。

## 测试规则

测试按依赖分层：

- Core：纯逻辑、固定时间、尽量全分支覆盖。
- Data：临时数据库、事务、并发和迁移行为；禁止读写真实用户目录。
- Services：替换外部依赖，验证编排、失败路径和状态变化。
- UI：只验证信号、控件状态和用户流程；需要图形环境时标记 `gui`。
- 手动测试：必须标记 `manual`，不能成为默认测试门禁。
- macOS 系统调用：必须标记 `macos`，并提供可测试的 mock/替代路径。

新增测试必须正确使用 `@pytest.mark.gui`、`@pytest.mark.macos` 或 `@pytest.mark.manual`。
测试标记不是装饰用途：CI 的排除规则依赖它们准确反映测试依赖。

## 质量门禁

提交前至少运行：

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
.venv/bin/black --check src/
.venv/bin/pytest -m "not manual and not macos and not gui"
```

涉及类型或公共接口时增加：

```bash
./scripts/check.sh types
```

涉及 UI 时使用可用的 macOS 图形会话；无图形会话只能运行 offscreen 测试，不能据此宣称完整 UI 验证通过。
CI 是合并前的最终门禁，必须与本地命令保持一致。Black 版本以 `.pre-commit-config.yaml` 的固定版本为准，避免直接使用未锁定的最新版本造成格式漂移。当前 mypy 的忽略项是历史债务，新增代码不得扩大忽略范围。

统一检查入口为 `scripts/check.sh`；单项调试可使用其子命令：

```bash
./scripts/check.sh lint
./scripts/check.sh format
./scripts/check.sh types
./scripts/check.sh test
```

每次提交前还要确认：

- `git diff --check` 无空白错误；
- 没有数据库、日志、构建产物、凭据或本机配置进入暂存区；
- 修复类变更有回归测试，公共接口变更有调用方和文档同步；
- 测试失败时记录真实失败原因，不用扩大 marker 排除范围掩盖失败。

## 变更原则

- 先写清用户可观察的行为，再决定实现位置。
- 修 bug 时补回归测试；新增功能同时补正常、边界和失败路径测试。
- 保持公开接口兼容；确需变更时同步更新调用方、测试和变更记录。
- 不提交 `.venv`、数据库、日志、构建产物、密钥或本机配置。
- 代码注释解释原因和约束，不重复代码表面行为。
- 优先小步提交；一个提交只解决一个可描述的问题，便于审查、回滚和定位回归。
