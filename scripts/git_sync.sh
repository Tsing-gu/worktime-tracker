#!/usr/bin/env bash

# Safe repository synchronization helper.
# Usage: ./scripts/git_sync.sh {status|pull|push|sync}

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

current_branch="$(git branch --show-current)"
if [[ -z "$current_branch" ]]; then
  echo "错误：当前处于 detached HEAD，不能自动同步。" >&2
  exit 1
fi

remote="origin"
remote_ref="$remote/$current_branch"

require_clean_tree() {
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "错误：工作区有未提交改动，请先提交或暂存后再执行同步。" >&2
    git status --short
    exit 1
  fi
}

show_status() {
  git status --short --branch
  git fetch --dry-run --prune "$remote"
  if git show-ref --verify --quiet "refs/remotes/$remote_ref"; then
    ahead="$(git rev-list --count "$remote_ref..$current_branch")"
    behind="$(git rev-list --count "$current_branch..$remote_ref")"
    echo "同步状态：ahead=$ahead, behind=$behind ($remote_ref)"
  else
    echo "同步状态：远端尚未发现对应分支 $remote_ref"
  fi
}

pull_changes() {
  require_clean_tree
  git fetch --prune "$remote"
  git rebase "$remote_ref"
}

push_changes() {
  require_clean_tree
  git push --set-upstream "$remote" "$current_branch"
}

sync_changes() {
  pull_changes
  push_changes
}

case "${1:-status}" in
  status) show_status ;;
  pull) pull_changes ;;
  push) push_changes ;;
  sync) sync_changes ;;
  *)
    echo "用法：$0 {status|pull|push|sync}" >&2
    exit 2
    ;;
esac
