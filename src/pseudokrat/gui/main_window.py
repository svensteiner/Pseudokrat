"""PySide6-Hauptfenster für Pseudokrat (Phase 2 — Live- und Datei-Tab)."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pseudokrat import __version__
from pseudokrat.gui.controller import GuiController, GuiError
from pseudokrat.gui.preview_widget import PIIPreviewWidget
from pseudokrat.gui.tray import PseudokratTrayIcon, attach_tray_icon


class FileDropList(QListWidget):
    """Liste mit Drag-and-Drop-Annahme für unterstützte Dateiformate."""

    def __init__(self, accepted_suffixes: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accepted = {s.lower() for s in accepted_suffixes}
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt-Signatur
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt-Signatur
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt-Signatur
        added = 0
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in self._accepted and self.add_path(path):
                added += 1
        if added:
            event.acceptProposedAction()
        else:
            event.ignore()

    def add_path(self, path: Path) -> bool:
        """Fügt einen Pfad hinzu, ohne Duplikate. Liefert True, wenn neu."""
        text = str(path)
        for row in range(self.count()):
            if self.item(row).text() == text:
                return False
        self.addItem(text)
        return True

    def paths(self) -> list[Path]:
        return [Path(self.item(row).text()) for row in range(self.count())]


class MainWindow(QMainWindow):
    """Hauptfenster: Profil-Auswahl + Live- und Datei-Tab."""

    def __init__(self, controller: GuiController | None = None) -> None:
        super().__init__()
        self._controller = controller or GuiController()
        self.setWindowTitle(f"Pseudokrat — v{__version__}")
        self.resize(960, 720)

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        self._build_profile_row(root_layout)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("tabs")
        root_layout.addWidget(self.tabs, stretch=1)

        self.tabs.addTab(self._build_live_tab(), "Live")
        self.tabs.addTab(self._build_files_tab(), "Datei")
        self.tabs.addTab(self._build_profiles_tab(), "Profile")

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Kein Profil geöffnet.")

        self._update_action_buttons_enabled(False)
        self._refresh_profiles()

        self.tray_icon: PseudokratTrayIcon = attach_tray_icon(self, parent=self)

    # --- builders -------------------------------------------------------------

    def _build_profile_row(self, root_layout: QVBoxLayout) -> None:
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profil:"))
        self.profile_input = QLineEdit("default")
        self.profile_input.setObjectName("profile_input")
        profile_row.addWidget(self.profile_input)
        profile_row.addWidget(QLabel("Master-Passwort:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setObjectName("password_input")
        profile_row.addWidget(self.password_input)
        self.open_button = QPushButton("Profil öffnen")
        self.open_button.setObjectName("open_button")
        self.open_button.clicked.connect(self._open_profile)
        profile_row.addWidget(self.open_button)
        root_layout.addLayout(profile_row)

    def _build_live_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Eingabe (Klartext):"))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setObjectName("input_edit")
        self.input_edit.setPlaceholderText(
            "Hier den zu anonymisierenden Text einfügen — kein Klartext verlässt die Maschine."
        )
        layout.addWidget(self.input_edit, stretch=1)

        button_row = QHBoxLayout()
        self.preview_button = QPushButton("Vorschau")
        self.preview_button.setObjectName("preview_button")
        self.preview_button.setToolTip(
            "Erkannte PII farbig markieren — Mapping wird nicht verändert."
        )
        self.preview_button.clicked.connect(self._preview)
        self.anonymize_button = QPushButton("Anonymisieren →")
        self.anonymize_button.setObjectName("anonymize_button")
        self.anonymize_button.clicked.connect(self._anonymize)
        self.deanonymize_button = QPushButton("← Deanonymisieren")
        self.deanonymize_button.setObjectName("deanonymize_button")
        self.deanonymize_button.clicked.connect(self._deanonymize)
        self.copy_button = QPushButton("Ausgabe kopieren")
        self.copy_button.setObjectName("copy_button")
        self.copy_button.clicked.connect(self._copy_output)
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.anonymize_button)
        button_row.addWidget(self.deanonymize_button)
        button_row.addStretch(1)
        button_row.addWidget(self.copy_button)
        layout.addLayout(button_row)

        layout.addWidget(QLabel("Vorschau (farbiges Highlight pro Kategorie):"))
        self.preview_edit = PIIPreviewWidget(tab)
        layout.addWidget(self.preview_edit, stretch=1)

        layout.addWidget(QLabel("Ausgabe:"))
        self.output_edit = QPlainTextEdit()
        self.output_edit.setObjectName("output_edit")
        self.output_edit.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.output_edit.setFont(mono)
        layout.addWidget(self.output_edit, stretch=1)
        return tab

    def _build_files_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        suffixes = self._controller.supported_file_suffixes()
        hint = ", ".join(suffixes) if suffixes else "(keine)"
        layout.addWidget(
            QLabel(
                "Dateien hier ablegen (Drag & Drop) oder über Hinzufügen "
                f"auswählen. Unterstützt: {hint}"
            )
        )

        self.file_list = FileDropList(accepted_suffixes=suffixes, parent=tab)
        self.file_list.setObjectName("file_list")
        layout.addWidget(self.file_list, stretch=1)

        file_buttons = QHBoxLayout()
        self.add_files_button = QPushButton("Hinzufügen…")
        self.add_files_button.setObjectName("add_files_button")
        self.add_files_button.clicked.connect(self._add_files_via_dialog)
        self.remove_files_button = QPushButton("Entfernen")
        self.remove_files_button.setObjectName("remove_files_button")
        self.remove_files_button.clicked.connect(self._remove_selected_files)
        self.clear_files_button = QPushButton("Liste leeren")
        self.clear_files_button.setObjectName("clear_files_button")
        self.clear_files_button.clicked.connect(self.file_list.clear)
        file_buttons.addWidget(self.add_files_button)
        file_buttons.addWidget(self.remove_files_button)
        file_buttons.addWidget(self.clear_files_button)
        file_buttons.addStretch(1)
        layout.addLayout(file_buttons)

        action_row = QHBoxLayout()
        self.anonymize_files_button = QPushButton("Dateien anonymisieren")
        self.anonymize_files_button.setObjectName("anonymize_files_button")
        self.anonymize_files_button.clicked.connect(self._anonymize_files)
        self.deanonymize_files_button = QPushButton("Dateien deanonymisieren")
        self.deanonymize_files_button.setObjectName("deanonymize_files_button")
        self.deanonymize_files_button.clicked.connect(self._deanonymize_files)
        action_row.addWidget(self.anonymize_files_button)
        action_row.addWidget(self.deanonymize_files_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        layout.addWidget(QLabel("Protokoll:"))
        self.files_log = QPlainTextEdit()
        self.files_log.setObjectName("files_log")
        self.files_log.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.files_log.setFont(mono)
        layout.addWidget(self.files_log, stretch=1)
        return tab

    # --- public api (für Tests) -----------------------------------------------

    @property
    def controller(self) -> GuiController:
        return self._controller

    def _update_action_buttons_enabled(self, enabled: bool) -> None:
        self.preview_button.setEnabled(enabled)
        self.anonymize_button.setEnabled(enabled)
        self.deanonymize_button.setEnabled(enabled)
        self.copy_button.setEnabled(enabled)
        self.anonymize_files_button.setEnabled(enabled)
        self.deanonymize_files_button.setEnabled(enabled)

    # --- slots: Profil --------------------------------------------------------

    def _open_profile(self) -> None:
        name = self.profile_input.text()
        password = self.password_input.text()
        try:
            self._controller.open_profile(name, password, disable_ml=True)
        except GuiError as exc:
            QMessageBox.warning(self, "Profil konnte nicht geöffnet werden", str(exc))
            return
        self._update_action_buttons_enabled(True)
        self.statusBar().showMessage(f"Profil '{name}' geöffnet.")

    # --- slots: Live ----------------------------------------------------------

    def _preview(self) -> None:
        text = self.input_edit.toPlainText()
        if not text:
            self.preview_edit.clear_preview()
            self.statusBar().showMessage("Vorschau: kein Text in der Eingabe.")
            return
        try:
            spans = self._controller.preview(text)
        except GuiError as exc:
            QMessageBox.warning(self, "Fehler", str(exc))
            return
        self.preview_edit.set_preview(text, spans)
        counts: dict[str, int] = {}
        for s in spans:
            counts[s.category] = counts.get(s.category, 0) + 1
        total = sum(counts.values())
        details = ", ".join(f"{k}={v}" for k, v in counts.items()) or "keine"
        self.statusBar().showMessage(f"Vorschau: {total} Entität(en) ({details}).")

    def _anonymize(self) -> None:
        text = self.input_edit.toPlainText()
        try:
            anonymized, counts = self._controller.anonymize(text)
        except GuiError as exc:
            QMessageBox.warning(self, "Fehler", str(exc))
            return
        self.output_edit.setPlainText(anonymized)
        total = sum(counts.values())
        details = ", ".join(f"{k}={v}" for k, v in counts.items()) or "keine"
        self.statusBar().showMessage(f"Anonymisiert: {total} Entität(en) ({details}).")

    def _deanonymize(self) -> None:
        text = self.input_edit.toPlainText()
        try:
            restored, resolved, missing = self._controller.deanonymize(text)
        except GuiError as exc:
            QMessageBox.warning(self, "Fehler", str(exc))
            return
        self.output_edit.setPlainText(restored)
        self.statusBar().showMessage(
            f"Deanonymisiert: {resolved} aufgelöst, {missing} unbekannte Platzhalter."
        )

    def _copy_output(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(self.output_edit.toPlainText())
        self.statusBar().showMessage("Ausgabe in Zwischenablage kopiert.")

    # --- slots: Dateien -------------------------------------------------------

    def _add_files_via_dialog(self) -> None:
        suffixes = self._controller.supported_file_suffixes()
        patterns = " ".join(f"*{s}" for s in suffixes)
        filter_str = f"Unterstützte Dateien ({patterns});;Alle Dateien (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "Dateien wählen", "", filter_str)
        added = 0
        for raw in paths:
            if self.file_list.add_path(Path(raw)):
                added += 1
        if added:
            self.statusBar().showMessage(f"{added} Datei(en) hinzugefügt.")

    def _remove_selected_files(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _anonymize_files(self) -> None:
        self._run_files(deanonymize=False)

    def _deanonymize_files(self) -> None:
        self._run_files(deanonymize=True)

    def _run_files(self, *, deanonymize: bool) -> None:
        paths = self.file_list.paths()
        if not paths:
            self.statusBar().showMessage("Keine Dateien in der Liste.")
            return
        op_label = "Deanonymisiert" if deanonymize else "Anonymisiert"
        success = 0
        for path in paths:
            try:
                result = self._controller.process_file(path, deanonymize=deanonymize)
            except GuiError as exc:
                self.files_log.appendPlainText(f"[FEHLER] {path}: {exc}")
                continue
            success += 1
            self.files_log.appendPlainText(
                f"[{op_label}] {path.name} → {result.output_path} "
                f"({result.segments_processed} Segmente)"
            )
        self.statusBar().showMessage(f"{op_label}: {success}/{len(paths)} Datei(en) erfolgreich.")

    # --- builder: Profile-Tab -------------------------------------------------

    def _build_profiles_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)

        layout.addWidget(
            QLabel(
                "Vorhandene Mandantenprofile. Mapping-Anzahl wird aus dem "
                "(passwortfreien) Header gelesen — Klartexte bleiben verschlüsselt."
            )
        )

        self.profiles_table = QTableWidget(0, 3, tab)
        self.profiles_table.setObjectName("profiles_table")
        self.profiles_table.setHorizontalHeaderLabels(["Profilname", "Mappings", "Angelegt"])
        self.profiles_table.verticalHeader().setVisible(False)
        self.profiles_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.profiles_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.profiles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.profiles_table, stretch=1)

        refresh_row = QHBoxLayout()
        self.refresh_profiles_button = QPushButton("Aktualisieren")
        self.refresh_profiles_button.setObjectName("refresh_profiles_button")
        self.refresh_profiles_button.clicked.connect(self._refresh_profiles)
        refresh_row.addWidget(self.refresh_profiles_button)
        refresh_row.addStretch(1)
        layout.addLayout(refresh_row)

        layout.addWidget(QLabel("Neues Profil anlegen:"))
        new_row = QHBoxLayout()
        new_row.addWidget(QLabel("Name:"))
        self.new_profile_name_input = QLineEdit()
        self.new_profile_name_input.setObjectName("new_profile_name_input")
        new_row.addWidget(self.new_profile_name_input)
        new_row.addWidget(QLabel("Master-Passwort:"))
        self.new_profile_password_input = QLineEdit()
        self.new_profile_password_input.setObjectName("new_profile_password_input")
        self.new_profile_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        new_row.addWidget(self.new_profile_password_input)
        self.create_profile_button = QPushButton("Profil anlegen")
        self.create_profile_button.setObjectName("create_profile_button")
        self.create_profile_button.clicked.connect(self._create_profile)
        new_row.addWidget(self.create_profile_button)
        layout.addLayout(new_row)

        audit_row = QHBoxLayout()
        self.verify_audit_button = QPushButton("Audit-Log der offenen Session prüfen")
        self.verify_audit_button.setObjectName("verify_audit_button")
        self.verify_audit_button.clicked.connect(self._verify_audit_log)
        audit_row.addWidget(self.verify_audit_button)
        self.audit_status_label = QLabel("—")
        self.audit_status_label.setObjectName("audit_status_label")
        audit_row.addWidget(self.audit_status_label, stretch=1)
        layout.addLayout(audit_row)

        return tab

    # --- slots: Profile-Tab ---------------------------------------------------

    def _refresh_profiles(self) -> None:
        summaries = self._controller.list_profile_summaries()
        self.profiles_table.setRowCount(len(summaries))
        for row, summary in enumerate(summaries):
            self.profiles_table.setItem(row, 0, QTableWidgetItem(summary.name))
            self.profiles_table.setItem(row, 1, QTableWidgetItem(str(summary.mapping_count)))
            self.profiles_table.setItem(row, 2, QTableWidgetItem(summary.created_utc))

    def _create_profile(self) -> None:
        name = self.new_profile_name_input.text().strip()
        password = self.new_profile_password_input.text()
        if not name:
            self.statusBar().showMessage("Bitte einen Profilnamen eingeben.")
            return
        if not password:
            self.statusBar().showMessage("Bitte ein Master-Passwort eingeben.")
            return
        try:
            summary = self._controller.create_profile(name, password)
        except GuiError as exc:
            QMessageBox.warning(self, "Profil konnte nicht angelegt werden", str(exc))
            self.statusBar().showMessage(str(exc))
            return
        self.new_profile_name_input.clear()
        self.new_profile_password_input.clear()
        self._refresh_profiles()
        self.statusBar().showMessage(f"Profil '{summary.name}' angelegt.")

    def _verify_audit_log(self) -> None:
        if self._controller.session is None:
            self.audit_status_label.setText("Kein Profil geöffnet.")
            self.statusBar().showMessage("Kein Profil geöffnet — Audit-Log nicht prüfbar.")
            return
        try:
            ok = self._controller.verify_audit()
        except GuiError as exc:
            self.audit_status_label.setText(str(exc))
            self.statusBar().showMessage(str(exc))
            return
        if ok:
            self.audit_status_label.setText("Hash-Kette gültig.")
            self.statusBar().showMessage("Audit-Log: Hash-Kette gültig.")
        else:
            self.audit_status_label.setText("MANIPULATION ERKANNT")
            self.statusBar().showMessage("Audit-Log: MANIPULATION ERKANNT.")

    # --- Tray-Host-API (vom Tray-Icon aufgerufen) ----------------------------

    def show_from_tray(self) -> None:
        """Stelle das Hauptfenster aus dem Tray wieder her und fokussiere es."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def focus_profile_input(self) -> None:
        """Wechsle auf den Profil-Eingang, damit ein Profil-Wechsel möglich ist."""
        self.profile_input.setFocus()
        self.profile_input.selectAll()

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt-Signatur
        self._controller.close()
        super().closeEvent(event)  # type: ignore[arg-type]


def build_application(argv: Sequence[str] | None = None) -> QApplication:
    args = list(argv) if argv is not None else sys.argv
    app = QApplication.instance()
    if app is None:
        app = QApplication(args)
    app.setApplicationName("Pseudokrat")
    app.setApplicationVersion(__version__)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    return app  # type: ignore[return-value]


def run(argv: Sequence[str] | None = None) -> int:
    """Startet die GUI und zeigt beim allerersten Start den Wizard.

    Wenn auf der Maschine noch kein Profil existiert, läuft vor dem
    Hauptfenster :class:`FirstStartWizard` (§9 Megaprompt). Bricht der
    Nutzer den Wizard ab, wird das Hauptfenster trotzdem gestartet —
    so ist sichergestellt, dass auch ein Power-User, der lieber per
    CLI anlegt, sofort weiterarbeiten kann.
    """
    from pseudokrat.gui.controller import GuiController
    from pseudokrat.gui.wizard import FirstStartWizard, first_start_required

    app = build_application(argv)
    window = MainWindow()
    controller = window.controller
    if isinstance(controller, GuiController) and first_start_required(controller):
        wizard = FirstStartWizard(controller, parent=window)
        wizard.exec()
        if wizard.created_profile is not None:
            window.profile_input.setText(wizard.created_profile.name)
            window._refresh_profiles()  # noqa: SLF001 - Tab im selben Modul
    window.show()
    return int(app.exec())
