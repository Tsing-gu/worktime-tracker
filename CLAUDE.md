# 编码规则（强制）

所有功能实现必须遵循以下规则，AI 和人类开发者均适用。

## 1. 一个功能一个文件

- 每个功能用**一个文件**实现，文件内用**类封装**
- 其他功能需要调用时，引用该文件，通过**传参方式**调用
- 不允许模块级散装函数（纯工具函数如 `utils/` 下除外）

## 2. 面向对象

- 所有功能必须类封装，不允许模块级散装函数
- 状态通过实例属性管理，通过方法暴露查询/操作接口
- 内部状态用 `_` 前缀标记私有，外部只通过公开方法访问
- 不用 `@staticmethod` 承担本应属于实例的逻辑

## 3. 事务边界

- 数据层通过 Repository 模式操作，有事务边界
- 多步操作用 `with self.transaction() as conn:` 包裹，自动 commit/rollback
- 连接复用，不允许每次调用重新 `get_connection() + close()`

## 4. 目录结构

- `src/` 次级目录按**层级 + 功能混合**分类：
  - `data/` — 数据存储（Database 基类 + 4 Repository）
  - `core/` — 纯业务逻辑（Calculator / HolidayService / Tracker / date_utils）
  - `services/` — 服务编排（WorktimeService / Exporter / UpdateService）
  - `ui/` — 界面层（MainWindow / Theme / 各弹窗）
  - `utils/` — 工具层（无状态纯函数）

## 5. 全功能解耦

- 所有功能解耦，不允许散装现象
- 依赖通过构造期注入（Repository / Calculator / 配置参数）
- 不允许跨层直接引用：UI 不 import data，core 不 import data

## 6. 分层依赖规则

```
UI ──→ Services ──→ Core
       │              │
       └──→ Data ←────┘
```

- **UI 层**只调 `services` 层，禁止 `from src.data import ...`
- **Core 层**通过构造期注入 Repository，不直接 `import database`
- **Data 层**是唯一直接操作 SQLite 的层
- **Utils 层**无状态纯函数，可被任意层调用

## 7. 同步更新调用关系

- 每次更新版本 / CHANGELOG / 发版时，**同步更新 `ARCHITECTURE.md`**
- 新增/删除/重命名类或方法 → 更新调用关系图和模块依赖表
- 新增/删除文件 → 更新目录结构表
- 规则本身变更 → 同步更新 `CLAUDE.md` 和 `docs/CODING_RULES.md`
