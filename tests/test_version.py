"""
test_version - 版本管理 + CHANGELOG 单元测试
=============================================

覆盖 src/utils/version.py：
- get_version：读 VERSION 文件
- _bump_version：版本号递增（minor / patch）
- record_change：bump 版本 + 写 CHANGELOG 条目
- 边界：无效类型、打包环境调用、文件不存在

用 monkeypatch 替换 _VERSION_FILE 和 _CHANGELOG_FILE 指向 tmp_path，
不污染真实的 VERSION 和 CHANGELOG.md。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

from src.utils import version as version_module
from src.utils.version import (
    _bump_version,
    get_version,
    record_change,
)


@pytest.fixture
def version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离的 VERSION 文件，初始写入 0.15.3。"""
    f = tmp_path / "VERSION"
    f.write_text("0.15.3", encoding="utf-8")
    monkeypatch.setattr(version_module, "_VERSION_FILE", str(f))
    return f


@pytest.fixture
def changelog_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离的 CHANGELOG.md 文件（空）。"""
    f = tmp_path / "CHANGELOG.md"
    f.write_text("", encoding="utf-8")
    monkeypatch.setattr(version_module, "_CHANGELOG_FILE", str(f))
    return f


class TestGetVersion:
    """get_version：读 VERSION 文件。"""

    def test_reads_current_version(self, version_file: Path) -> None:
        """正常读取版本号。"""
        assert get_version() == "0.15.3"

    def test_missing_file_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """VERSION 文件不存在时返回 "0.0.0"。"""
        monkeypatch.setattr(version_module, "_VERSION_FILE", str(tmp_path / "nonexistent"))
        assert get_version() == "0.0.0"

    def test_strips_whitespace(self, version_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """版本号首尾空白被 strip。"""
        version_file.write_text("  0.16.0\n", encoding="utf-8")
        assert get_version() == "0.16.0"


class TestBumpVersion:
    """_bump_version：版本号递增。"""

    def test_patch_bump(self) -> None:
        """patch 级别：末位 +1。"""
        assert _bump_version("0.15.3", "patch") == "0.15.4"

    def test_minor_bump(self) -> None:
        """minor 级别：中位 +1，末位置 0。"""
        assert _bump_version("0.15.3", "minor") == "0.16.0"

    def test_major_bumps_as_minor(self) -> None:
        """major 级别：正式版前不 bump MAJOR，转为 bump MINOR。"""
        assert _bump_version("0.15.3", "major") == "0.16.0"

    def test_bump_from_two_part_version(self) -> None:
        """两位版本号补齐到三位。"""
        assert _bump_version("0.15", "patch") == "0.15.1"

    def test_bump_patch_carries(self) -> None:
        """patch 多次 bump 正确递增。"""
        v = "0.15.3"
        v = _bump_version(v, "patch")
        assert v == "0.15.4"
        v = _bump_version(v, "patch")
        assert v == "0.15.5"

    def test_bump_minor_resets_patch(self) -> None:
        """minor bump 后 patch 位置 0。"""
        v = _bump_version("0.15.9", "minor")
        assert v == "0.16.0"


class TestRecordChange:
    """record_change：bump 版本 + 写 CHANGELOG。"""

    def test_added_bumps_patch(self, version_file: Path, changelog_file: Path) -> None:
        """added 类型 bump PATCH。"""
        new_ver = record_change("added", "新增某功能")
        assert new_ver == "0.15.4"
        assert version_file.read_text(encoding="utf-8") == "0.15.4"

    def test_fixed_bumps_patch(self, version_file: Path, changelog_file: Path) -> None:
        """fixed 类型 bump PATCH。"""
        new_ver = record_change("fixed", "修复某问题")
        assert new_ver == "0.15.4"

    def test_changed_bumps_minor(self, version_file: Path, changelog_file: Path) -> None:
        """changed 类型 bump MINOR。"""
        new_ver = record_change("changed", "变更某功能")
        assert new_ver == "0.16.0"
        assert version_file.read_text(encoding="utf-8") == "0.16.0"

    def test_removed_bumps_minor(self, version_file: Path, changelog_file: Path) -> None:
        """removed 类型 bump MINOR。"""
        new_ver = record_change("removed", "移除某功能")
        assert new_ver == "0.16.0"

    def test_changelog_entry_format(self, version_file: Path, changelog_file: Path) -> None:
        """CHANGELOG 条目格式正确：标题 + 类型 + 描述 + 日期。"""
        record_change("added", "新增手动补录功能")
        content = changelog_file.read_text(encoding="utf-8")

        today_str = date.today().isoformat()
        assert f"## [0.15.4] - {today_str}" in content
        assert "**新增**: 新增手动补录功能" in content

    def test_changelog_entry_on_top(self, version_file: Path, changelog_file: Path) -> None:
        """新条目置顶，已有内容保留在后。"""
        # 先写一条已有条目
        changelog_file.write_text(
            "## [0.15.3] - 2026-07-28\n\n- **修复**: 旧问题\n\n",
            encoding="utf-8",
        )

        record_change("added", "新功能")
        content = changelog_file.read_text(encoding="utf-8")

        # 新条目应在顶部
        assert content.index("0.15.4") < content.index("0.15.3")
        # 旧条目保留
        assert "0.15.3" in content
        assert "旧问题" in content

    def test_multiple_changes_accumulate(self, version_file: Path, changelog_file: Path) -> None:
        """连续多次 record_change 累积递增版本。"""
        v1 = record_change("added", "功能 A")
        v2 = record_change("fixed", "修复 B")
        v3 = record_change("changed", "变更 C")

        assert v1 == "0.15.4"
        assert v2 == "0.15.5"
        assert v3 == "0.16.0"

        content = changelog_file.read_text(encoding="utf-8")
        # 三条都在
        assert "功能 A" in content
        assert "修复 B" in content
        assert "变更 C" in content
        # 最新版在最顶
        assert content.index("0.16.0") < content.index("0.15.5")
        assert content.index("0.15.5") < content.index("0.15.4")

    def test_invalid_type_raises(self, version_file: Path, changelog_file: Path) -> None:
        """无效变更类型抛 ValueError。"""
        with pytest.raises(ValueError, match="无效的变更类型"):
            record_change("invalid_type", "描述")

    def test_frozen_env_raises(
        self,
        version_file: Path,
        changelog_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """打包环境（sys.frozen=True）调用抛 RuntimeError。"""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        with pytest.raises(RuntimeError, match="不可在打包环境调用"):
            record_change("added", "描述")

    def test_changelog_type_labels(self, version_file: Path, changelog_file: Path) -> None:
        """四种变更类型的中文标签正确。"""
        record_change("added", "desc-a")
        # fixed/changed/removed 都从 0.15.4 起继续 bump
        record_change("fixed", "desc-f")
        record_change("changed", "desc-c")
        record_change("removed", "desc-r")

        content = changelog_file.read_text(encoding="utf-8")
        assert "**新增**: desc-a" in content
        assert "**修复**: desc-f" in content
        assert "**变更**: desc-c" in content
        assert "**移除**: desc-r" in content
