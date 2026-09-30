"""Offscreen desktop journey using artificial Excel and real background jobs."""

import os

import pytest
from openpyxl import Workbook

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from pseudokrat.gui.controller import GuiController  # noqa: E402
from pseudokrat.gui.ki_project_tab import KiProjectTab  # noqa: E402


def test_desktop_prepare_and_review_gate(qtbot, tmp_path, data_dir):
    controller = GuiController()
    controller.open_profile("gui_test", "synthetic-test-password", disable_ml=True)
    tab = KiProjectTab(controller)
    qtbot.addWidget(tab)
    book = Workbook()
    book.active.append(["Name", "Betrag"])
    book.active.append(["Sondername", 123.5])
    path = tmp_path / "sample.xlsx"
    book.save(path)
    tab.files.addItem(str(path))
    tab.project_path.setText(str(tmp_path / "project"))
    tab.terms.setPlainText("Sondername")
    tab.update_session(True)
    tab.prepare_button.click()
    qtbot.waitUntil(lambda: tab.job is None, timeout=30000)
    assert (tmp_path / "project" / "zuordnung.enc").exists()
    assert not tab.publish_button.isEnabled()
    tab.reviewed.setChecked(True)
    assert not tab.publish_button.isEnabled()
    tab.numeric_risk.setChecked(True)
    assert tab.publish_button.isEnabled()
    tab.publish_button.click()
    qtbot.waitUntil(lambda: tab.job is None, timeout=30000)
    assert (tmp_path / "project" / "KI-Paket.zip").exists()
    controller.close()


def test_no_profile_disables_actions(qtbot):
    tab = KiProjectTab(GuiController())
    qtbot.addWidget(tab)
    tab.update_session(False)
    assert not tab.prepare_button.isEnabled()
    assert not tab.publish_button.isEnabled()
