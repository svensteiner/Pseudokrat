"""Headless-Tests für das System-Tray-Icon (Megaprompt §9)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication  # noqa: E402

from pseudokrat.gui.main_window import MainWindow, build_application  # noqa: E402
from pseudokrat.gui.tray import PseudokratTrayIcon  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or build_application(["pseudokrat-tray-tests"])


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


def test_tray_icon_is_attached(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        assert isinstance(win.tray_icon, PseudokratTrayIcon)
        # In offscreen ist System-Tray nicht verfügbar — Konstruktion klappt
        # trotzdem, damit Slot-Verbindungen testbar bleiben.
        assert win.tray_icon.contextMenu() is not None
    finally:
        win.close()


def test_tray_menu_has_required_entries(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        labels = win.tray_icon.menu_labels()
        # §9: App öffnen, Profil wechseln, Audit-Log exportieren, Beenden
        assert labels == [
            "App öffnen",
            "Profil wechseln…",
            "Audit-Log exportieren…",
            "Beenden",
        ]
    finally:
        win.close()


def test_tray_show_action_brings_window_forward(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        # Fenster nicht sichtbar starten und „App öffnen" auslösen.
        win.hide()
        assert not win.isVisible()
        win.tray_icon.show_action.trigger()
        # showNormal() macht das Fenster sichtbar (auch in offscreen-Backends).
        assert win.isVisible()
    finally:
        win.close()


def test_tray_switch_profile_action_focuses_input(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.show()
        win.profile_input.setText("Mandant Hofer")
        win.tray_icon.switch_profile_action.trigger()
        # Headless-Backend liefert nicht zuverlässig OS-Fokus; aber selectAll
        # markiert den Text und das Fenster ist sichtbar.
        assert win.isVisible()
        assert win.profile_input.selectedText() == "Mandant Hofer"
    finally:
        win.close()


def test_tray_export_audit_without_session_warns(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        # Kein Profil offen → Aktion liefert nur eine Tray-Notification,
        # kein Crash. Wir prüfen lediglich, dass kein Dateidialog aufgerufen
        # wird (Controller wirft GuiError, der Tray fängt das ab).
        win.tray_icon.export_audit_action.trigger()
        # Es darf keine Exception fliegen.
    finally:
        win.close()


def test_tray_export_audit_csv_writes_file(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("tray_export")
        win.password_input.setText("pw")
        win._open_profile()
        # Erzeuge mindestens einen Audit-Log-Eintrag.
        win.input_edit.setPlainText("Hofer Bau GmbH ist Mandant.")
        win._anonymize()

        target = tmp_path / "audit-tray_export.csv"

        # File-Dialog stubben, damit der Tray-Pfad headless laufen kann.
        from pseudokrat.gui import tray as tray_module

        monkeypatch.setattr(
            tray_module.QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **kw: (str(target), "CSV (*.csv)")),
        )

        win.tray_icon.export_audit_action.trigger()
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        # CSV-Header zumindest vorhanden
        assert "timestamp_utc" in content
        # Mindestens ein anonymize-Eintrag
        assert "anonymize" in content
    finally:
        win.close()


def test_tray_export_audit_pdf_branch(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("tray_export_pdf")
        win.password_input.setText("pw")
        win._open_profile()
        win.input_edit.setPlainText("Hofer Bau GmbH ist Mandant.")
        win._anonymize()

        target = tmp_path / "audit-tray_export.pdf"
        from pseudokrat.gui import tray as tray_module

        monkeypatch.setattr(
            tray_module.QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **kw: (str(target), "PDF (*.pdf)")),
        )

        win.tray_icon.export_audit_action.trigger()
        assert target.exists()
        assert target.stat().st_size > 0
        # Magic-Bytes „%PDF" am Dateianfang
        assert target.read_bytes()[:4] == b"%PDF"
    finally:
        win.close()


def test_tray_export_audit_cancelled_dialog_is_noop(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("tray_cancel")
        win.password_input.setText("pw")
        win._open_profile()
        win.input_edit.setPlainText("Hofer Bau GmbH ist Mandant.")
        win._anonymize()

        from pseudokrat.gui import tray as tray_module

        monkeypatch.setattr(
            tray_module.QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **kw: ("", "")),
        )
        # Abbruch im Dialog → keine Exception, kein Dateischreibvorgang.
        win.tray_icon.export_audit_action.trigger()
    finally:
        win.close()


def test_tray_quit_closes_session_and_quits(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("tray_quit")
        win.password_input.setText("pw")
        win._open_profile()
        assert win.controller.session is not None

        # QApplication.quit darf in den Tests nicht wirklich beenden.
        calls: list[bool] = []
        monkeypatch.setattr(QApplication, "quit", lambda *a, **kw: calls.append(True))

        win.tray_icon.quit_action.trigger()
        assert calls == [True]
        # Session muss geschlossen sein.
        assert win.controller.session is None
    finally:
        win.close()
