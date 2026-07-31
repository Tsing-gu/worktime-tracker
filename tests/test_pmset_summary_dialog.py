"""
test_pmset_summary_dialog - pmset 推断弹窗测试
=================================================

覆盖 src/ui/pmset_summary_dialog.py 的 PmsetSummaryDialogUI：
- 初始化时触发子线程加载 pmset 推断
- _render_table：表格内容渲染
- _configure_apply_button：按钮启用/禁用逻辑
- _on_apply_start / _on_apply_end：应用记录到 DB
- _format_existing_status：已有记录状态文本

用 pytest-qt 的 qtbot fixture 驱动 Qt 事件循环，tmp_db 隔离数据库，
monkeypatch mock tracking_service 避免真实 pmset 调用。
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6 import QtWidgets

from src.data.models import PmsetDailySummary
from src.services.factory import ServiceFactory
from src.ui.pmset_summary_dialog import PmsetSummaryDialogUI

pytestmark = pytest.mark.gui


@pytest.fixture
def factory(tmp_db: Path, sample_holidays, monkeypatch) -> ServiceFactory:
    """构造测试用 ServiceFactory。"""
    f = ServiceFactory(db_path=str(tmp_db))
    f.settings_service.init()
    f.holiday_repo.save_year(2026, sample_holidays)
    # 所有测试默认只验证 UI；需要数据的用例在自身作用域覆盖该 mock。
    monkeypatch.setattr(
        f.tracking_service,
        "get_recent_pmset_summary",
        lambda days=7, **kwargs: [],
    )
    return f


@pytest.fixture
def mock_summaries() -> list[PmsetDailySummary]:
    """构造 7 天 mock 推断数据。

    包含各种状态：
    - 今天：无记录，有推断
    - 前 1 天：仅上班记录，有推断
    - 前 2 天：完整记录，有推断
    - 前 3 天：请假记录，有推断
    - 前 4 天：手动记录，有推断
    - 前 5 天：无推断（pmset 失败）
    - 前 6 天：无记录无推断
    """
    return [
        PmsetDailySummary(
            work_date=date(2026, 7, 15),
            first_active=datetime(2026, 7, 15, 9, 0),
            last_active=datetime(2026, 7, 15, 18, 0),
            has_start_record=False,
            has_end_record=False,
            source=None,
            leave_type=None,
        ),
        PmsetDailySummary(
            work_date=date(2026, 7, 14),
            first_active=datetime(2026, 7, 14, 9, 15),
            last_active=datetime(2026, 7, 14, 19, 30),
            has_start_record=True,
            has_end_record=False,
            source="auto",
            leave_type=None,
        ),
        PmsetDailySummary(
            work_date=date(2026, 7, 13),
            first_active=datetime(2026, 7, 13, 9, 0),
            last_active=datetime(2026, 7, 13, 18, 0),
            has_start_record=True,
            has_end_record=True,
            source="auto",
            leave_type=None,
        ),
        PmsetDailySummary(
            work_date=date(2026, 7, 12),
            first_active=datetime(2026, 7, 12, 10, 0),
            last_active=datetime(2026, 7, 12, 17, 0),
            has_start_record=False,
            has_end_record=False,
            source=None,
            leave_type="annual",
        ),
        PmsetDailySummary(
            work_date=date(2026, 7, 11),
            first_active=datetime(2026, 7, 11, 9, 30),
            last_active=datetime(2026, 7, 11, 20, 0),
            has_start_record=True,
            has_end_record=True,
            source="manual",
            leave_type=None,
        ),
        PmsetDailySummary(
            work_date=date(2026, 7, 10),
            first_active=None,
            last_active=None,
            has_start_record=False,
            has_end_record=False,
            source=None,
            leave_type=None,
        ),
        PmsetDailySummary(
            work_date=date(2026, 7, 9),
            first_active=None,
            last_active=None,
            has_start_record=False,
            has_end_record=False,
            source=None,
            leave_type=None,
        ),
    ]


class TestFormatExistingStatus:
    """_format_existing_status：已有记录状态文本。"""

    def test_leave_record(self, qtbot, factory) -> None:
        """请假记录 → 显示「请假-类型」。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            leave_type="annual",
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        result = dlg._format_existing_status(s)
        assert "请假-年假" in result
        dlg.close()

    def test_full_record(self, qtbot, factory) -> None:
        """完整记录 → 显示「已记录」。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            has_start_record=True,
            has_end_record=True,
            source="auto",
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        result = dlg._format_existing_status(s)
        assert "已记录" in result
        dlg.close()

    def test_only_start(self, qtbot, factory) -> None:
        """仅上班记录 → 显示「仅上班」。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            has_start_record=True,
            has_end_record=False,
            source="auto",
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        result = dlg._format_existing_status(s)
        assert "仅上班" in result
        dlg.close()

    def test_no_record(self, qtbot, factory) -> None:
        """无记录 → 显示「无记录」。"""
        s = PmsetDailySummary(work_date=date(2026, 7, 15))
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        result = dlg._format_existing_status(s)
        assert "无记录" in result
        dlg.close()

    def test_close_cancels_and_waits_for_worker(self, qtbot, factory, monkeypatch) -> None:
        """关闭窗口时取消并等待正在运行的回溯线程。"""
        started = threading.Event()

        def blocking_summary(days=7, cancel_event=None):
            started.set()
            assert cancel_event is not None
            cancel_event.wait(timeout=2)
            return []

        monkeypatch.setattr(
            factory.tracking_service,
            "get_recent_pmset_summary",
            blocking_summary,
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        qtbot.waitUntil(started.is_set, timeout=1000)

        dlg.close()

        assert dlg._cancel_event.is_set()
        assert not dlg._workers


class TestConfigureApplyButton:
    """_configure_apply_button：按钮启用/禁用逻辑。"""

    @pytest.fixture
    def dialog(self, qtbot, factory, monkeypatch) -> PmsetSummaryDialogUI:
        """构造对话框，mock get_recent_pmset_summary 避免子线程阻塞。"""
        monkeypatch.setattr(
            factory.tracking_service,
            "get_recent_pmset_summary",
            lambda days=7, **kwargs: [],
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        return dlg

    def test_leave_disables_both(self, dialog: PmsetSummaryDialogUI) -> None:
        """有请假记录 → 上班/下班按钮都禁用。"""
        s = PmsetDailySummary(work_date=date(2026, 7, 15), leave_type="annual")
        btn_start = QtWidgets.QPushButton()
        btn_end = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn_start, s, is_start=True)
        dialog._configure_apply_button(btn_end, s, is_start=False)
        assert not btn_start.isEnabled()
        assert not btn_end.isEnabled()
        assert "请假" in btn_start.toolTip()

    def test_manual_source_disables_both(self, dialog: PmsetSummaryDialogUI) -> None:
        """手动记录 → 上班/下班按钮都禁用。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            has_start_record=True,
            has_end_record=True,
            source="manual",
        )
        btn_start = QtWidgets.QPushButton()
        btn_end = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn_start, s, is_start=True)
        dialog._configure_apply_button(btn_end, s, is_start=False)
        assert not btn_start.isEnabled()
        assert not btn_end.isEnabled()
        assert "手动" in btn_start.toolTip()

    def test_no_first_active_disables_start(self, dialog: PmsetSummaryDialogUI) -> None:
        """无推断上班时间 → 应用上班按钮禁用。"""
        s = PmsetDailySummary(work_date=date(2026, 7, 15), first_active=None)
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=True)
        assert not btn.isEnabled()
        assert "未检测" in btn.toolTip()

    def test_has_start_record_disables_start(self, dialog: PmsetSummaryDialogUI) -> None:
        """已有上班记录 → 应用上班按钮禁用。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            first_active=datetime(2026, 7, 15, 9, 0),
            has_start_record=True,
            source="auto",
        )
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=True)
        assert not btn.isEnabled()
        assert "已有上班记录" in btn.toolTip()

    def test_normal_state_enables_start(self, dialog: PmsetSummaryDialogUI) -> None:
        """正常状态（有推断、无记录） → 应用上班按钮启用。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            first_active=datetime(2026, 7, 15, 9, 0),
        )
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=True)
        assert btn.isEnabled()
        assert btn.toolTip() == ""

    def test_no_last_active_disables_end(self, dialog: PmsetSummaryDialogUI) -> None:
        """无推断下班时间 → 应用下班按钮禁用。"""
        s = PmsetDailySummary(work_date=date(2026, 7, 15), last_active=None)
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=False)
        assert not btn.isEnabled()
        assert "未检测" in btn.toolTip()

    def test_no_start_record_disables_end(self, dialog: PmsetSummaryDialogUI) -> None:
        """无上班记录 → 应用下班按钮禁用。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            last_active=datetime(2026, 7, 15, 18, 0),
            has_start_record=False,
        )
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=False)
        assert not btn.isEnabled()
        assert "无上班记录" in btn.toolTip()

    def test_has_end_record_disables_end(self, dialog: PmsetSummaryDialogUI) -> None:
        """已有下班记录 → 应用下班按钮禁用。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            last_active=datetime(2026, 7, 15, 18, 0),
            has_start_record=True,
            has_end_record=True,
            source="auto",
        )
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=False)
        assert not btn.isEnabled()
        assert "已有下班记录" in btn.toolTip()

    def test_normal_state_enables_end(self, dialog: PmsetSummaryDialogUI) -> None:
        """正常状态（有推断、有上班、无下班） → 应用下班按钮启用。"""
        s = PmsetDailySummary(
            work_date=date(2026, 7, 15),
            last_active=datetime(2026, 7, 15, 18, 0),
            has_start_record=True,
            has_end_record=False,
            source="auto",
        )
        btn = QtWidgets.QPushButton()
        dialog._configure_apply_button(btn, s, is_start=False)
        assert btn.isEnabled()
        assert btn.toolTip() == ""


class TestRenderTable:
    """_render_table：表格内容渲染。"""

    def test_renders_all_rows(self, qtbot, factory, mock_summaries, monkeypatch) -> None:
        """渲染所有行，行数 == summaries 长度。"""
        monkeypatch.setattr(
            factory.tracking_service,
            "get_recent_pmset_summary",
            lambda days=7, **kwargs: mock_summaries,
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        # 等子线程完成（_on_loaded 触发 _render_table）
        qtbot.waitUntil(lambda: dlg.table.rowCount() == len(mock_summaries), timeout=2000)

        assert dlg.table.rowCount() == len(mock_summaries)
        # 第一行日期文本
        date_item = dlg.table.item(0, 0)
        assert date_item is not None
        assert "2026-07-15" in date_item.text()
        # 第一行推断上班时间
        first_item = dlg.table.item(0, 1)
        assert first_item is not None
        assert first_item.text() == "09:00"
        # 第一行推断下班时间
        last_item = dlg.table.item(0, 2)
        assert last_item is not None
        assert last_item.text() == "18:00"
        dlg.close()

    def test_empty_summaries_renders_zero_rows(self, qtbot, factory, monkeypatch) -> None:
        """空列表渲染 0 行。"""
        monkeypatch.setattr(
            factory.tracking_service,
            "get_recent_pmset_summary",
            lambda days=7, **kwargs: [],
        )
        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        qtbot.waitUntil(lambda: dlg.table.rowCount() == 0, timeout=2000)

        assert dlg.table.rowCount() == 0
        dlg.close()


class TestApplyActions:
    """_on_apply_start / _on_apply_end：应用记录到 DB。"""

    def test_apply_start_calls_tracking_service(
        self, qtbot, factory, mock_summaries, monkeypatch
    ) -> None:
        """点击应用上班按钮调用 tracking_service.apply_pmset_start_time。"""
        called = []

        def fake_apply_start(work_date, start_time):
            called.append((work_date, start_time))
            return True

        monkeypatch.setattr(
            factory.tracking_service,
            "get_recent_pmset_summary",
            lambda days=7, **kwargs: mock_summaries,
        )
        monkeypatch.setattr(
            factory.tracking_service,
            "apply_pmset_start_time",
            fake_apply_start,
        )
        # mock _refresh_db_state 避免其调用真实 DB
        monkeypatch.setattr(factory.tracking_service, "_worktime_repo", MagicMock())
        # mock _show_msg 避免模态 exec 阻塞测试
        monkeypatch.setattr(PmsetSummaryDialogUI, "_show_msg", lambda self, t, x: None)

        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        qtbot.waitUntil(lambda: dlg.table.rowCount() == len(mock_summaries), timeout=2000)

        # 点击第一行（今天，正常状态）的应用上班按钮
        dlg._on_apply_start(0)
        # 等子线程完成
        qtbot.waitUntil(lambda: len(called) == 1, timeout=2000)

        assert len(called) == 1
        work_date, start_time = called[0]
        assert work_date == date(2026, 7, 15)
        assert start_time == datetime(2026, 7, 15, 9, 0)
        dlg.close()

    def test_apply_end_calls_tracking_service(
        self, qtbot, factory, mock_summaries, monkeypatch
    ) -> None:
        """点击应用下班按钮调用 tracking_service.apply_pmset_end_time。"""
        called = []

        def fake_apply_end(work_date, end_time):
            called.append((work_date, end_time))
            return True

        monkeypatch.setattr(
            factory.tracking_service,
            "get_recent_pmset_summary",
            lambda days=7, **kwargs: mock_summaries,
        )
        monkeypatch.setattr(
            factory.tracking_service,
            "apply_pmset_end_time",
            fake_apply_end,
        )
        monkeypatch.setattr(factory.tracking_service, "_worktime_repo", MagicMock())
        # mock _show_msg 避免模态 exec 阻塞测试
        monkeypatch.setattr(PmsetSummaryDialogUI, "_show_msg", lambda self, t, x: None)

        dlg = PmsetSummaryDialogUI(parent=None, factory=factory)
        qtbot.addWidget(dlg)
        qtbot.waitUntil(lambda: dlg.table.rowCount() == len(mock_summaries), timeout=2000)

        # 点击第二行（前 1 天，有上班无下班）的应用下班按钮
        dlg._on_apply_end(1)
        qtbot.waitUntil(lambda: len(called) == 1, timeout=2000)

        assert len(called) == 1
        work_date, end_time = called[0]
        assert work_date == date(2026, 7, 14)
        assert end_time == datetime(2026, 7, 14, 19, 30)
        dlg.close()
