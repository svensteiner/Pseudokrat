"""Headless-Smoketest des PySide6-Hauptfensters (offscreen)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Wir setzen die Qt-Platform-Plugin-Variable BEVOR PySide6 importiert wird.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication  # noqa: E402

from pseudokrat.gui.main_window import MainWindow, build_application  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or build_application(["pseudokrat-tests"])


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


def test_window_constructs(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        assert win.windowTitle().startswith("Pseudokrat")
        # Aktion-Buttons sind initial deaktiviert.
        assert not win.preview_button.isEnabled()
        assert not win.anonymize_button.isEnabled()
        assert not win.deanonymize_button.isEnabled()
        assert not win.copy_button.isEnabled()
    finally:
        win.close()


def test_preview_highlights_spans_with_category_colors(qt_app: QApplication) -> None:
    from pseudokrat.gui.preview_widget import color_for_category

    win = MainWindow()
    try:
        win.profile_input.setText("ui_preview")
        win.password_input.setText("pw")
        win._open_profile()
        assert win.preview_button.isEnabled()

        sample = "Hofer Bau GmbH zahlt auf AT611904300234573201."
        win.input_edit.setPlainText(sample)
        win._preview()

        # Vorschau-Editor zeigt den Originaltext (read-only).
        assert win.preview_edit.toPlainText() == sample
        assert win.preview_edit.isReadOnly()

        # Highlight-Hintergrund auf der "Hofer Bau GmbH"-Position
        # entspricht der COMPANY-Farbe; Klartextposition außerhalb der
        # Spans hat den Default-Hintergrund.
        company_pos = sample.index("Hofer Bau GmbH")
        cursor = win.preview_edit.textCursor()
        cursor.setPosition(company_pos + 1)
        company_bg = cursor.charFormat().background().color()
        assert company_bg.name().upper() == color_for_category("COMPANY").name().upper()

        # Tooltip ist gesetzt und enthält die Kategorie.
        tip = cursor.charFormat().toolTip()
        assert "COMPANY" in tip

        # IBAN-Stelle hat die IBAN-Farbe (anderer Pastellton).
        iban_pos = sample.index("AT61")
        cursor.setPosition(iban_pos + 2)
        iban_bg = cursor.charFormat().background().color()
        assert iban_bg.name().upper() == color_for_category("IBAN").name().upper()
        assert company_bg.name() != iban_bg.name()

        # Statusbar meldet erkannte Entitäten.
        msg = win.statusBar().currentMessage()
        assert "Vorschau" in msg
        assert "COMPANY=1" in msg
        assert "IBAN=1" in msg

        # Erneute echte Anonymisierung darf trotz Vorschau bei _001 starten —
        # die Vorschau hat das Mapping nicht persistiert.
        win._anonymize()
        assert "<COMPANY_001>" in win.output_edit.toPlainText()
    finally:
        win.close()


def test_preview_with_empty_input_clears(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("ui_preview_empty")
        win.password_input.setText("pw")
        win._open_profile()
        win.input_edit.setPlainText("")
        # erst etwas Vorschau-Inhalt setzen, damit clear messbar wird
        win.preview_edit.setPlainText("ALT")
        win._preview()
        assert win.preview_edit.toPlainText() == ""
        assert "kein Text" in win.statusBar().currentMessage()
    finally:
        win.close()


def test_open_profile_enables_buttons(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("gui_smoke")
        win.password_input.setText("pw")
        win._open_profile()
        assert win.anonymize_button.isEnabled()
        assert win.deanonymize_button.isEnabled()
        assert win.copy_button.isEnabled()
        assert "gui_smoke" in win.statusBar().currentMessage()
    finally:
        win.close()


def test_full_anonymize_then_deanonymize_via_ui(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("ui_round")
        win.password_input.setText("pw")
        win._open_profile()
        win.input_edit.setPlainText("Hofer Bau GmbH ist Mandant.")
        win._anonymize()
        anonymized = win.output_edit.toPlainText()
        assert "<COMPANY_001>" in anonymized
        # Dann die Ausgabe zurück in die Eingabe übertragen und deanonymisieren.
        win.input_edit.setPlainText(anonymized)
        win._deanonymize()
        restored = win.output_edit.toPlainText()
        assert "Hofer Bau GmbH" in restored
    finally:
        win.close()


def test_copy_button_writes_clipboard(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.output_edit.setPlainText("ZWISCHENABLAGE-INHALT")
        win._copy_output()
        clipboard = QApplication.clipboard()
        # Auf offscreen-Plattformen ist Clipboard verfügbar, aber leer-initialisiert.
        assert clipboard.text() == "ZWISCHENABLAGE-INHALT"
        assert "Zwischenablage" in win.statusBar().currentMessage()
    finally:
        win.close()


def test_window_has_live_and_files_tabs(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert labels[:2] == ["Live", "Datei"]
        # Datei-Tab-Buttons starten deaktiviert.
        assert not win.anonymize_files_button.isEnabled()
        assert not win.deanonymize_files_button.isEnabled()
    finally:
        win.close()


def test_file_list_add_and_dedup(qt_app: QApplication, tmp_path: Path) -> None:
    win = MainWindow()
    try:
        p = tmp_path / "a.txt"
        p.write_text("x", encoding="utf-8")
        assert win.file_list.add_path(p) is True
        assert win.file_list.add_path(p) is False
        assert win.file_list.count() == 1
        assert win.file_list.paths() == [p]
    finally:
        win.close()


def test_anonymize_files_pipeline(qt_app: QApplication, tmp_path: Path) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("gui_files")
        win.password_input.setText("pw")
        win._open_profile()

        src = tmp_path / "brief.txt"
        src.write_text("Hofer Bau GmbH ist Mandant.", encoding="utf-8")
        win.file_list.add_path(src)

        win._anonymize_files()
        out = src.with_name("brief.anon.txt")
        assert out.exists()
        assert "<COMPANY_001>" in out.read_text(encoding="utf-8")
        assert "erfolgreich" in win.statusBar().currentMessage()

        # Protokoll erwähnt den Anonymisier-Schritt
        log = win.files_log.toPlainText()
        assert "Anonymisiert" in log
        assert "brief.txt" in log
    finally:
        win.close()


def test_anonymize_files_empty_list_yields_status(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("gui_empty_files")
        win.password_input.setText("pw")
        win._open_profile()
        win._anonymize_files()
        assert "Keine Dateien" in win.statusBar().currentMessage()
    finally:
        win.close()


def test_anonymize_files_logs_error_on_missing(qt_app: QApplication, tmp_path: Path) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("gui_missing_files")
        win.password_input.setText("pw")
        win._open_profile()
        ghost = tmp_path / "ghost.txt"
        win.file_list.add_path(ghost)  # Datei existiert nicht
        win._anonymize_files()
        assert "[FEHLER]" in win.files_log.toPlainText()
    finally:
        win.close()


def test_window_has_profiles_tab(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        assert win.tabs.count() == 3
        labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert labels == ["Live", "Datei", "Profile"]
    finally:
        win.close()


def test_profiles_tab_lists_existing_profiles(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("plist_a")
        win.password_input.setText("pw")
        win._open_profile()
        win.input_edit.setPlainText("Hofer Bau GmbH ist Mandant.")
        win._anonymize()

        # Refresh sollte den neuen Eintrag aufnehmen
        win._refresh_profiles()
        rows = win.profiles_table.rowCount()
        assert rows >= 1
        names = [win.profiles_table.item(r, 0).text() for r in range(rows)]
        assert "plist_a" in names
        idx = names.index("plist_a")
        # Spalte 1: Mapping-Count
        assert win.profiles_table.item(idx, 1).text() == "1"
    finally:
        win.close()


def test_profiles_tab_create_new_profile(qt_app: QApplication, tmp_path: Path) -> None:
    win = MainWindow()
    try:
        win.new_profile_name_input.setText("brand_new")
        win.new_profile_password_input.setText("pw")
        win._create_profile()

        names = [win.profiles_table.item(r, 0).text() for r in range(win.profiles_table.rowCount())]
        assert "brand_new" in names
        assert "angelegt" in win.statusBar().currentMessage()
        # Eingabefelder werden geleert
        assert win.new_profile_name_input.text() == ""
        assert win.new_profile_password_input.text() == ""
    finally:
        win.close()


def test_profiles_tab_create_requires_name_and_password(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.new_profile_name_input.setText("")
        win.new_profile_password_input.setText("pw")
        win._create_profile()
        assert "Profilname" in win.statusBar().currentMessage()

        win.new_profile_name_input.setText("only_name")
        win.new_profile_password_input.setText("")
        win._create_profile()
        assert "Passwort" in win.statusBar().currentMessage()
    finally:
        win.close()


def test_profiles_tab_audit_verify_no_session(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win._verify_audit_log()
        # Ohne offenes Profil → klare Status-Meldung
        assert "Kein Profil" in win.statusBar().currentMessage()
        assert "Kein Profil" in win.audit_status_label.text()
    finally:
        win.close()


def test_profiles_tab_audit_verify_ok(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        win.profile_input.setText("audit_ok")
        win.password_input.setText("pw")
        win._open_profile()
        win.input_edit.setPlainText("Hofer Bau GmbH ist Mandant.")
        win._anonymize()

        win._verify_audit_log()
        assert "gültig" in win.audit_status_label.text().lower()
    finally:
        win.close()
