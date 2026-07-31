# Git 工作流

本项目使用 `origin/main` 作为唯一稳定主线。远端地址为：

```text
https://github.com/Tsing-gu/worktime-tracker.git
```

## 初始化

```bash
git clone https://github.com/Tsing-gu/worktime-tracker.git
cd worktime-tracker
git config --local fetch.prune true
git config --local pull.rebase true
git config --local rebase.autoStash true
git config --local push.default simple
git config --local push.autoSetupRemote true
```

依赖安装和 pre-commit 安装见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 日常同步

推荐使用仓库内脚本，避免在有未提交改动时误拉取或覆盖工作：

```bash
./scripts/git_sync.sh status   # 查看工作区及 ahead/behind
./scripts/git_sync.sh pull     # fetch --prune + rebase origin/当前分支
./scripts/git_sync.sh push     # 推送当前分支并建立 upstream
./scripts/git_sync.sh sync     # 先 pull，再 push
```

脚本会拒绝在 dirty worktree 或 detached HEAD 状态下执行拉取/推送。发生冲突时，按 Git 提示解决后执行：

```bash
git add <resolved-files>
git rebase --continue
```

如果需要放弃本次 rebase，只执行明确的恢复命令：

```bash
git rebase --abort
```

## 分支与提交

- `main` 只接收已验证的变更；日常开发使用 `feature/<简短主题>` 或 `fix/<简短主题>` 分支，并通过 PR 或明确审查后合并。
- 禁止对 `main` 使用 `git push --force`、`git reset --hard` 或未经确认的历史改写。
- 提交使用 Conventional Commits：`feat`、`fix`、`refactor`、`test`、`docs`、`chore`、`style`。
- 每次提交聚焦一个主题，提交前必须检查 `git diff` 和 `git status`。
- 发布提交必须同步更新 `VERSION`、`CHANGELOG.md` 和 `appcast.xml`，并通过打包验证；只有发布负责人确认后才直接推送 `main`。

## 权限与凭据

- HTTPS 凭据由 macOS Keychain (`osxkeychain`) 管理，不把 token、密码或私钥写入仓库。
- 当前环境的公开拉取正常，但推送认证需要先完成一次 GitHub 登录：推荐执行 `gh auth login`；也可以把已加入 GitHub 账户的 SSH 公钥配置到本机后，将 push URL 切换为 `git@github.com:Tsing-gu/worktime-tracker.git`。
- 本机发现 `~/.ssh/id_ed25519`，但仅凭文件存在不能证明该公钥已加入 GitHub，也不能据此自动切换远端。
- 只读检查远端可用：`git ls-remote origin`。
- 推送前确认当前分支、远端和待推送提交：`git branch -vv`、`git log origin/main..HEAD`。
- 发现远端 URL、账户或权限异常时先停止，不通过脚本绕过认证或改写远端配置。
