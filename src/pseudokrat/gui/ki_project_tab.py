"""Desktop workflow: local preview, reviewed cloud package and private Spark handoff."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pseudokrat.gui.controller import GuiController
from pseudokrat.ki_project import (
    ProjectError,
    prepare_original_workspace,
    prepare_project,
    publish_project,
    restore_file,
)


class _Job(QThread):
    result = Signal(str)

    def __init__(self, action: Callable[[], Path], parent: QWidget) -> None:
        super().__init__(parent)
        self.action = action

    def run(self) -> None:
        try:
            path = self.action()
            self.result.emit("Fertig: " + str(path))
        except ProjectError as exc:
            self.result.emit("Nicht freigegeben: " + str(exc))
        except Exception:
            # Native/parser errors may contain original text and paths.
            self.result.emit("Verarbeitung fehlgeschlagen. Dateien, Profil und Ziel lokal prüfen.")


class KiProjectTab(QWidget):
    def __init__(self, controller: GuiController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.job: _Job | None = None
        self._session_open = controller.session is not None
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Originaldateien bleiben bei dir. Excel-Zahlen bleiben unverändert.\n"
            "1. Lokale Vorschau erstellen → 2. Prüfen und KI-Paket freigeben → "
            "3. Code auf dem eigenen Spark mit Originaldaten umsetzen."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.files = QListWidget()
        layout.addWidget(self.files)
        file_actions = QHBoxLayout()
        add = QPushButton("Excel / Word hinzufügen")
        add.clicked.connect(self._add_files)
        file_actions.addWidget(add)
        remove = QPushButton("Ausgewählte entfernen")
        remove.clicked.connect(self._remove_files)
        file_actions.addWidget(remove)
        layout.addLayout(file_actions)
        self.terms = QPlainTextEdit()
        self.terms.setPlaceholderText("Zusätzliche Namen, Firmen, Kennungen oder Projekte – ein Begriff je Zeile (bleibt lokal).")
        self.terms.setMaximumHeight(90)
        layout.addWidget(self.terms)
        self.model_group = QGroupBox("Eigene KI zusätzlich verwenden (erhält Originaltext)")
        self.model_group.setCheckable(True)
        self.model_group.setChecked(False)
        model_layout = QVBoxLayout(self.model_group)
        self.model_endpoint = QLineEdit()
        self.model_endpoint.setPlaceholderText("Lokale API-Adresse, z. B. http://127.0.0.1:1234/v1")
        model_layout.addWidget(self.model_endpoint)
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("Exakte Modellkennung des eigenen Servers, z. B. GPT-OSS 120B")
        model_layout.addWidget(self.model_name)
        self.allow_lan = QCheckBox("Der gewählte Spark im privaten Netz gehört mir und darf Originaltext erhalten.")
        model_layout.addWidget(self.allow_lan)
        layout.addWidget(self.model_group)
        folder_row = QHBoxLayout()
        self.project_path = QLineEdit()
        self.project_path.setPlaceholderText("Neuer Projektordner oder vorhandenes KI-Projekt")
        self.project_path.textChanged.connect(self._reset_review)
        folder_row.addWidget(self.project_path)
        choose = QPushButton("Ordner wählen")
        choose.clicked.connect(self._choose_project)
        folder_row.addWidget(choose)
        layout.addLayout(folder_row)
        actions = QHBoxLayout()
        self.prepare_button = QPushButton("1. Vorschau erstellen")
        self.prepare_button.clicked.connect(self._prepare)
        actions.addWidget(self.prepare_button)
        self.preview_button = QPushButton("Vorschau öffnen")
        self.preview_button.clicked.connect(self._open_preview)
        actions.addWidget(self.preview_button)
        layout.addLayout(actions)
        self.reviewed = QCheckBox("Ich habe alle Vorschau-Dateien lokal auf verbleibende Identifikatoren geprüft.")
        self.numeric_risk = QCheckBox("Die unveränderten Zahlen und Merkmalskombinationen dürfen weitergegeben werden.")
        self.reviewed.toggled.connect(self._refresh)
        self.numeric_risk.toggled.connect(self._refresh)
        layout.addWidget(self.reviewed)
        layout.addWidget(self.numeric_risk)
        note = QLabel("Keine Anonymitätsgarantie: Echte Zahlen können eine Zuordnung ermöglichen. Bei verbleibender Zuordnung nur lokal arbeiten.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.publish_button = QPushButton("2. Geprüftes KI-Paket erstellen")
        self.publish_button.clicked.connect(self._publish)
        layout.addWidget(self.publish_button)
        final = QHBoxLayout()
        self.restore_button = QPushButton("Platzhalter zurückwandeln")
        self.restore_button.clicked.connect(self._restore)
        final.addWidget(self.restore_button)
        self.local_button = QPushButton("3. Originaldaten für Spark (vertraulich)")
        self.local_button.clicked.connect(self._local_workspace)
        final.addWidget(self.local_button)
        layout.addLayout(final)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self._refresh()

    def update_session(self, enabled: bool) -> None:
        self._session_open = enabled
        self._refresh()

    def _refresh(self) -> None:
        ready = self._session_open and self.job is None
        self.prepare_button.setEnabled(ready)
        self.restore_button.setEnabled(ready)
        self.local_button.setEnabled(ready)
        self.preview_button.setEnabled(self.job is None)
        self.publish_button.setEnabled(ready and self.reviewed.isChecked() and self.numeric_risk.isChecked())

    def _reset_review(self) -> None:
        self.reviewed.setChecked(False)
        self.numeric_risk.setChecked(False)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Originaldateien auswählen", "", "Excel / Word (*.xlsx *.docx)")
        existing = {self.files.item(i).text() for i in range(self.files.count())}
        for name in files:
            if name not in existing:
                self.files.addItem(name)

    def _remove_files(self) -> None:
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))

    def _choose_project(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Projekt oder übergeordneten Ordner auswählen")
        if name:
            path = Path(name)
            self.project_path.setText(str(path if (path / "zuordnung.enc").exists() else path / "KI-Projekt"))

    def _project(self) -> Path:
        if not self.project_path.text().strip():
            raise ProjectError("Projektordner auswählen.")
        return Path(self.project_path.text().strip())

    def _run(self, action: Callable[[], Path]) -> None:
        if self.job is not None:
            return
        self.job = _Job(action, self)
        self.job.result.connect(self.log.appendPlainText)
        self.job.finished.connect(self._finished)
        self._refresh()
        self.job.start()

    def _finished(self) -> None:
        if self.job is not None:
            self.job.deleteLater()
        self.job = None
        self._refresh()
        try:
            info = json.loads((self._project() / "pruefung.json").read_text("utf-8"))
            self.log.appendPlainText(
                f"Ersetzungen: {info['identity_replacements']}; numerische Kennungen: {info['numeric_identifiers']}; "
                f"erkannte Merkmalsspalten: {info['quasi_identifier_columns']}. Vorschau vollständig prüfen."
            )
        except (OSError, ValueError, KeyError):
            pass

    def _prepare(self) -> None:
        session = self.controller.session
        if session is None:
            return
        try:
            project = self._project()
        except ProjectError as exc:
            self.log.appendPlainText(str(exc))
            return
        paths = [Path(self.files.item(i).text()) for i in range(self.files.count())]
        terms = self.terms.toPlainText().splitlines()
        key = session.store.keys.fernet
        detector = None
        if self.model_group.isChecked():
            from pseudokrat.pii.local_project_detector import LocalProjectDetector

            try:
                detector = LocalProjectDetector(self.model_endpoint.text(), self.model_name.text(),
                                                allow_lan=self.allow_lan.isChecked())
            except ProjectError as exc:
                self.log.appendPlainText(str(exc))
                return
        self._reset_review()
        self._run(lambda: prepare_project(paths, project, key, terms=terms, detector=detector))

    def _publish(self) -> None:
        session = self.controller.session
        if session is None:
            return
        try:
            project = self._project()
        except ProjectError as exc:
            self.log.appendPlainText(str(exc))
            return
        key = session.store.keys.fernet
        reviewed, risk = self.reviewed.isChecked(), self.numeric_risk.isChecked()
        self._run(lambda: publish_project(project, key, reviewed=reviewed, accept_numeric_linkability=risk))

    def _open_preview(self) -> None:
        try:
            path = self._project() / "vorschau"
            if path.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        except ProjectError as exc:
            self.log.appendPlainText(str(exc))

    def _restore(self) -> None:
        session = self.controller.session
        if session is None:
            return
        try:
            project = self._project()
        except ProjectError as exc:
            self.log.appendPlainText(str(exc))
            return
        source, _ = QFileDialog.getOpenFileName(self, "Bearbeitete Datei mit Projekt-Platzhaltern", "", "Office (*.xlsx *.docx)")
        if not source:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Neue Original-Ausgabe", "", "Office (*.xlsx *.docx)")
        if dest:
            key = session.store.keys.fernet
            self._run(lambda: restore_file(project, key, Path(source), Path(dest)))

    def _local_workspace(self) -> None:
        session = self.controller.session
        if session is None:
            return
        try:
            project = self._project()
        except ProjectError as exc:
            self.log.appendPlainText(str(exc))
            return
        directory = QFileDialog.getExistingDirectory(self, "Vertraulichen lokalen Zielordner auswählen")
        if directory:
            key = session.store.keys.fernet
            destination = Path(directory) / "originaldaten"
            self._run(lambda: prepare_original_workspace(project, key, destination))
