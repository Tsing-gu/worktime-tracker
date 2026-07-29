# 贡献指南

本文档说明如何搭建开发环境并参与项目开发。

## 环境要求

- **Python 3.12+**（推荐 3.12.13，已验证可用）
- **macOS**（本项目依赖 macOS 系统调用 `ioreg` / `pmset` / `ipconfig` / `osascript`）
- **Git**

## 环境搭建

### 1. 克隆仓库

```bash
git clone https://github.com/Tsing-gu/worktime-tracker.git
cd worktime-tracker
```

### 2. 创建虚拟环境

```bash
python3.12 -m venv .venv
```

> 若系统没有 Python 3.12，可通过 [Homebrew](https://brew.sh/) 安装：`brew install python@3.12`

### 3. 安装依赖

```bash
# 运行时依赖
.venv/bin/pip install -r requirements.txt

# 开发依赖（测试 / 类型检查 / 代码风格 / 提交钩子）
.venv/bin/pip install -r requirements-dev.txt
```

**国内开发者**：若默认 PyPI 速度慢，可用清华镜像源加速：

```bash
.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt -r requirements-dev.txt
```

> 实测：PySide6 完整包约 440MB（Essentials 110MB + Addons 332MB），官方源耗时数十分钟，清华源约 1 分钟。

### 4. 安装 pre-commit 钩子

```bash
.venv/bin/pre-commit install
```

此后每次 `git commit` 会自动运行 ruff / black / mypy 检查，不通过则阻止提交。

### 5. 验证环境

```bash
# 运行测试
.venv/bin/pytest

# 类型检查
.venv/bin/mypy --config-file=pyproject.toml src/

# 代码风格检查
.venv/bin/ruff check src/
.venv/bin/ruff format --check src/
.venv/bin/black --check src/

# 手动跑 pre-commit 全量检查
.venv/bin/pre-commit run --all-files
```

## 开发工作流

### 日常开发

1. 激活虚拟环境（或全程用 `.venv/bin/python` / `.venv/bin/pytest` 等绝对路径）
2. 修改代码
3. 运行测试：`.venv/bin/pytest`
4. 提交：`git commit`（pre-commit 自动检查）

### IDE 配置

将 IDE 的 Python 解释器指向项目根目录的 `.venv/bin/python`：

- **VS Code**：`Cmd+Shift+P` → "Python: Select Interpreter" → 选择 `.venv/bin/python`
- **PyCharm**：`Preferences → Project → Python Interpreter` → 指向 `.venv/bin/python`

### 打包发布

```bash
bash scripts/build_dmg.sh
```

产物：`dist/WorkTimeTracker.dmg`

> 打包脚本会自动检查 `.venv/` 是否存在，若不存在会提示先创建虚拟环境并安装依赖。

## 项目结构

```
worktime-tracker/
├── main.py                  # 程序入口
├── src/
│   ├── config.py            # 全局配置常量
│   ├── core/                # 纯业务逻辑层
│   ├── data/                # 数据存储层（唯一操作 SQLite）
│   ├── services/            # 服务编排层
│   ├── ui/                  # 界面层（PySide6）
│   └── utils/               # 工具层（无状态纯函数）
├── tests/                   # 测试
├── docs/                    # 文档
├── scripts/                 # 脚本
├── resources/               # 资源文件
├── pyproject.toml           # 工程配置（pytest/mypy/ruff/black）
├── requirements.txt         # 运行时依赖
├── requirements-dev.txt     # 开发依赖
└── .pre-commit-config.yaml  # 提交钩子配置
```

## 编码规范

详见 [CLAUDE.md](CLAUDE.md) 和 [docs/CODING_RULES.md](docs/CODING_RULES.md)。

核心规则：
- 一个功能一个文件，文件内用类封装
- 面向对象，不允许模块级散装函数（`utils/` 下纯工具函数除外）
- 分层依赖：UI → Services → Core，Data 是唯一直接操作 SQLite 的层
- 数据层通过 Repository 模式操作，多步操作用 `with self.transaction() as conn:` 包裹

## 测试规范

- 测试框架：pytest
- 测试目录：`tests/`
- 运行：`.venv/bin/pytest`
- 覆盖率：`.venv/bin/pytest --cov=src --cov-report=term-missing`

测试标记：
- `@pytest.mark.manual`：手动交互测试，CI 与常规 pytest 跳过
- `@pytest.mark.macos`：依赖 macOS 系统调用，非 macOS 环境跳过
- `@pytest.mark.gui`：需图形环境的 UI 测试，CI 跳过

## 提交规范

commit message 格式（Conventional Commits）：

```
<type>: <description>

type 可选值：
- feat:     新功能
- fix:      修复 bug
- refactor: 重构（不改功能、不修 bug）
- docs:     文档
- style:    代码风格（不影响功能）
- test:     测试
- chore:    构建/工具/依赖
```

示例：
```
refactor: 拆分 WorktimeService 为 4 个子服务
fix: 修复跨天补录下班时间未对齐时间下限的问题
```

## 类型检查规范

- 类型检查工具：mypy
- 配置：`pyproject.toml` 的 `[tool.mypy]` 段
- 策略：分模块渐进收紧（Phase 0 宽松，后续阶段逐模块开启 strict）

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。
