"""
test_dialog_coordinator - 弹窗协调器测试
==========================================

覆盖 src/ui/dialog_coordinator.py 的 DialogCoordinator：
- open：统一打开非模态弹窗 + 自动管理 _busy/_pending
- busy：弹窗状态查询
- 并发弹窗拒绝（_busy=True 时 open 返回 False）
- msg_information / msg_warning / msg_question：消息提示框

用 pytest-qt 的 qtbot fixture 驱动 Qt 事件循环，tmp_db 隔离数据库。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtWidgets

from src.services.factory import ServiceFactory
from src.ui.dialog_coordinator import DialogCoordinator


@pytest.fixture
def factory(tmp_db: Path, sample_holidays, monkeypatch) -> ServiceFactory:
    """构造测试用 ServiceFactory（含已填充的 holiday / settings 仓储）。

    避免真实 HolidayService API 调用：手动创建 factory 后注入测试数据。
    """
    # 用真实 ServiceFactory 构造全部服务
    f = ServiceFactory()
    # 初始化数据库 + 设置
    f.settings_service.init()
    # 填充节假日
    f.holiday_repo.save_year(2026, sample_holidays)
    return f


@pytest.fixture
def coordinator(qtbot, factory: ServiceFactory) -> DialogCoordinator:
    """构造测试用 DialogCoordinator（qtbot 驱动 Qt 事件循环）。"""
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    return DialogCoordinator(parent, factory)


class TestOpen:
    """open：统一打开非模态弹窗。"""

    def test_open_sets_busy(self, coordinator: DialogCoordinator, qtbot) -> None:
        """open 后 busy 为 True。"""
        dlg = QtWidgets.QDialog(coordinator._parent)
        called = []

        def on_finished(code: int) -> None:
            called.append(code)

        result = coordinator.open(dlg, on_finished)

        assert result is True
        assert coordinator.busy is True
        # 清理
        dlg.close()

    def test_open_returns_false_when_busy(self, coordinator: DialogCoordinator, qtbot) -> None:
        """busy 时 open 返回 False，不打开新弹窗。"""
        dlg1 = QtWidgets.QDialog(coordinator._parent)
        coordinator.open(dlg1, lambda code: None)
        assert coordinator.busy is True

        dlg2 = QtWidgets.QDialog(coordinator._parent)
        result = coordinator.open(dlg2, lambda code: None)

        assert result is False
        # dlg2 未被 show
        assert not dlg2.isVisible()
        # 清理
        dlg1.close()

    def test_open_clears_busy_on_close(self, coordinator: DialogCoordinator, qtbot) -> None:
        """弹窗关闭后 busy 恢复 False，回调被调用。"""
        dlg = QtWidgets.QDialog(coordinator._parent)
        called = []

        def on_finished(code: int) -> None:
            called.append(code)

        coordinator.open(dlg, on_finished)
        assert coordinator.busy is True

        # 关闭弹窗
        dlg.done(QtWidgets.QDialog.Accepted)
        qtbot.waitUntil(lambda: not coordinator.busy, timeout=1000)

        assert coordinator.busy is False
        assert len(called) == 1
        assert called[0] == QtWidgets.QDialog.Accepted


class TestBusy:
    """busy 属性。"""

    def test_initial_busy_false(self, coordinator: DialogCoordinator) -> None:
        """初始状态 busy=False。"""
        assert coordinator.busy is False


class TestMsgBoxes:
    """msg_information / msg_warning / msg_question。"""

    def test_msg_information(self, coordinator: DialogCoordinator, qtbot) -> None:
        """msg_information 弹出对话框，标题和正文正确。"""
        dlg = coordinator.msg_information("标题", "内容")
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "标题"
        # 对话框内应有一个 QLabel 包含正文
        labels = dlg.findChildren(QtWidgets.QLabel)
        assert any("内容" in lbl.text() for lbl in labels)
        dlg.close()

    def test_msg_warning(self, coordinator: DialogCoordinator, qtbot) -> None:
        """msg_warning 弹出对话框，标题正确。"""
        dlg = coordinator.msg_warning("警告", "警告内容")
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "警告"
        dlg.close()

    def test_msg_question(self, coordinator: DialogCoordinator, qtbot) -> None:
        """msg_question 弹出对话框，含是/否两个按钮。"""
        dlg = coordinator.msg_question("确认", "是否继续？")
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "确认"
        # 对话框内应有两个 QPushButton（是 + 否）
        buttons = dlg.findChildren(QtWidgets.QPushButton)
        assert len(buttons) == 2
        btn_texts = {b.text() for b in buttons}
        assert btn_texts == {"是", "否"}
        dlg.close()

    def test_msg_question_triggers_on_yes(self, coordinator: DialogCoordinator, qtbot) -> None:
        """msg_question 点「是」触发 on_yes 回调。"""
        result = []
        dlg = coordinator.msg_question("确认", "是否继续？", on_yes=lambda: result.append(1))
        qtbot.addWidget(dlg)
        # 找到「是」按钮并点击
        buttons = dlg.findChildren(QtWidgets.QPushButton)
        yes_btn = next(b for b in buttons if b.text() == "是")
        yes_btn.click()
        assert result == [1]

    def test_msg_question_triggers_on_no(self, coordinator: DialogCoordinator, qtbot) -> None:
        """msg_question 点「否」触发 on_no 回调。"""
        result = []
        dlg = coordinator.msg_question("确认", "是否继续？", on_no=lambda: result.append(1))
        qtbot.addWidget(dlg)
        buttons = dlg.findChildren(QtWidgets.QPushButton)
        no_btn = next(b for b in buttons if b.text() == "否")
        no_btn.click()
        assert result == [1]


class TestOnEditStart:
    """on_edit_start：修改上班时间弹窗。"""

    def test_opens_edit_start_dialog(self, coordinator: DialogCoordinator, qtbot) -> None:
        """on_edit_start 打开 EditStartDialogUI。"""
        coordinator.on_edit_start()
        assert coordinator.busy is True
        # 清理
        if coordinator._pending is not None:
            coordinator._pending.close()


class TestOnSettings:
    """on_settings：设置弹窗。"""

    def test_opens_settings_dialog(self, coordinator: DialogCoordinator, qtbot) -> None:
        """on_settings 打开 SettingsDialogUI。"""
        coordinator.on_settings()
        assert coordinator.busy is True
        # 清理
        if coordinator._pending is not None:
            coordinator._pending.close()


class TestOnHistory:
    """on_history：日历历史弹窗。"""

    def test_opens_history_dialog(self, coordinator: DialogCoordinator, qtbot) -> None:
        """on_history 打开 CalendarHistoryDialogUI。"""
        coordinator.on_history()
        assert coordinator.busy is True
        # 清理
        if coordinator._pending is not None:
            coordinator._pending.close()


class TestOnLeave:
    """on_leave：请假弹窗。"""

    def test_opens_leave_dialog(self, coordinator: DialogCoordinator, qtbot) -> None:
        """on_leave 打开 LeaveDialogUI。"""
        coordinator.on_leave()
        assert coordinator.busy is True
        # 清理
        if coordinator._pending is not None:
            coordinator._pending.close()


class TestOnExport:
    """on_export：导出弹窗。"""

    def test_opens_export_dialog(self, coordinator: DialogCoordinator, qtbot) -> None:
        """on_export 打开导出确认 QDialog。"""
        coordinator.on_export()
        assert coordinator.busy is True
        # 清理
        if coordinator._pending is not None:
            coordinator._pending.close()


class TestCheckYesterdayConfirm:
    """check_yesterday_confirm：次日确认弹窗。"""

    def test_no_record_returns_silently(self, coordinator: DialogCoordinator, qtbot) -> None:
        """无待确认记录时不弹窗。"""
        coordinator.check_yesterday_confirm()
        # 无记录 → 不弹窗
        assert coordinator.busy is False

    def test_with_record_opens_dialog(
        self, coordinator: DialogCoordinator, qtbot, monkeypatch
    ) -> None:
        """有待确认记录时弹窗。"""
        from datetime import date, datetime

        # 固定 datetime.now 到有前一工作日记录的时间
        fixed_now = datetime(2026, 7, 15, 14, 0, 0)

        class _FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        monkeypatch.setattr("src.services.record_service.datetime", _FixedDatetime)
        monkeypatch.setattr("src.services.stats_service.datetime", _FixedDatetime)

        # 插入前一工作日（2026-07-14 周二）的未确认记录
        prev = date(2026, 7, 14)
        coordinator._record._worktime_repo.upsert(
            prev,
            start_time=datetime(2026, 7, 14, 9, 0, 0),
            end_time=datetime(2026, 7, 14, 17, 30, 0),
            total_hours=8.5,
            required_hours=8.0,
            source="auto",
            is_confirmed=0,
        )

        coordinator.check_yesterday_confirm()
        assert coordinator.busy is True
        # 清理
        if coordinator._pending is not None:
            coordinator._pending.close()


class TestConfirmResume:
    """confirm_resume：恢复计时确认。"""

    def test_opens_resume_dialog(self, coordinator: DialogCoordinator, qtbot) -> None:
        """confirm_resume 打开非模态确认对话框（是/否按钮）。"""
        coordinator.confirm_resume()
        # msg_question 不走 self.open()，不设置 _busy，但会创建并显示对话框
        # 验证：存在一个活跃的 QDialog（通过 QApplication.topLevelWidgets 查找）
        top_dialogs = [
            w
            for w in QtWidgets.QApplication.topLevelWidgets()
            if isinstance(w, QtWidgets.QDialog) and w.isVisible()
        ]
        assert len(top_dialogs) >= 1
        # 清理
        for d in top_dialogs:
            d.close()
