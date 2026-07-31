#!/usr/bin/env bash

# Single source of truth for local/CI quality checks.
# Usage: ./scripts/check.sh {lint|format|types|test|all}

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

ruff_bin="${RUFF_BIN:-.venv/bin/ruff}"
black_bin="${BLACK_BIN:-.venv/bin/black}"
mypy_bin="${MYPY_BIN:-.venv/bin/mypy}"
pytest_bin="${PYTEST_BIN:-.venv/bin/pytest}"

run_lint() {
  "$ruff_bin" check src/ tests/
}

run_format() {
  "$ruff_bin" format --check src/ tests/
  "$black_bin" --check src/
}

run_types() {
  "$mypy_bin" --config-file=pyproject.toml \
    --disable-error-code=attr-defined \
    --disable-error-code=assignment \
    --disable-error-code=type-arg \
    --disable-error-code=no-any-return \
    --disable-error-code=name-defined \
    --disable-error-code=return-value \
    --disable-error-code=import-untyped \
    --disable-error-code=call-overload \
    src/
}

run_test() {
  "$pytest_bin" -m "not manual and not macos and not gui"
}

case "${1:-all}" in
  lint) run_lint ;;
  format) run_format ;;
  types) run_types ;;
  test) run_test ;;
  all)
    run_lint
    run_format
    run_types
    run_test
    ;;
  *)
    echo "用法：$0 {lint|format|types|test|all}" >&2
    exit 2
    ;;
esac
