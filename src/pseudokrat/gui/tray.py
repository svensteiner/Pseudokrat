"""System-Tray-Icon mit Rechtsklick-Menü (Megaprompt §9).

Das Tray-Icon hält das Hauptfenster im System-Tray erreichbar, auch wenn der
Nutzer es schließt — typischer Workflow eines Background-Daemons für die
Zwischenablage-Hotkeys (siehe DECISIONS D-024).

Das Menü liefert genau die vier in §9 geforderten Einträge:

* **App öffnen** — Hauptfenster wiederherstellen und in den Vordergrund.
* **Profil wechseln…** — Fokus auf den Profil-Eingang im Hauptfenster.
* **Audit-Log exportieren…** — Speichern-Dialog für CSV/PDF.
* **Beenden** — sauberer Shutdown (Session schließen, App quitten).

Das Icon ist UI-thin: alle Aktionen delegieren an den :class:`GuiController`
oder an :class:`MainWindow`. Für headless-Tests genügt es, die Aktionen direkt
auszulösen (``tray.show_action.trigger()`` etc.) — ein sichtbares Tray-Icon
ist nicht erforderlich.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

if TYPE_CHECKING:  # pragma: no cover - nur Typprüfung
    from pseudokrat.gui.controller import GuiController


class _TrayHost(Protocol):
    """Schmale Schnittstelle, die das Tray-Icon auf dem Hauptfenster nutzt."""

    def show_from_tray(self) -> None: ...

    def focus_profile_input(self) -> None: ...

    @property
    def controller(self) -> GuiController: ...


def _fallback_icon() -> QIcon:
    """Erzeuge ein einfaches Platzhalter-Icon, falls kein Theme-Icon vorliegt."""
    style = QApplication.style()
    if style is not None:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if not icon.isNull():
            return icon
    pixmap = QPixmap(16, 16)
    pixmap.fill()
    painter = QPainter(pixmap)
    try:
        painter.drawRect(0, 0, 15, 15)
    finally:
        painter.end()
    return QIcon(pixmap)


class PseudokratTrayIcon(QSystemTrayIcon):
    """Tray-Icon mit Rechtsklick-Menü gemäß Megaprompt §9."""

    def __init__(self, host: _TrayHost, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self.setIcon(_fallback_icon())
        self.setToolTip("Pseudokrat — lokal-only Anonymisierung")

        menu = QMenu()
        self.show_action: QAction = menu.addAction("App öffnen")
        self.switch_profile_action: QAction = menu.addAction("Profil wechseln…")
        self.export_audit_action: QAction = menu.addAction("Audit-Log exportieren…")
        menu.addSeparator()
        self.quit_action: QAction = menu.addAction("Beenden")
        self.setContextMenu(menu)
        self._menu = menu  # halte Referenz, sonst GC'd Qt das Menü weg

        self.show_action.triggered.connect(self._on_show)
        self.switch_profile_action.triggered.connect(self._on_switch_profile)
        self.export_audit_action.triggered.connect(self._on_export_audit)
        self.quit_action.triggered.connect(self._on_quit)
        self.activated.connect(self._on_activated)

    # --- Slot-Handler ---------------------------------------------------------

    def _on_show(self) -> None:
        self._host.show_from_tray()

    def _on_switch_profile(self) -> None:
        self._host.show_from_tray()
        self._host.focus_profile_input()

    def _on_export_audit(self) -> None:
        controller = self._host.controller
        if controller.session is None:
            self.showMessage(
                "Pseudokrat",
                "Kein Profil geöffnet — Audit-Log nicht verfügbar.",
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )
            return
        target, selected_filter = QFileDialog.getSaveFileName(
            None,
            "Audit-Log exportieren",
            f"audit-{controller.session.profile_name}.csv",
            "CSV (*.csv);;PDF (*.pdf)",
        )
        if not target:
            return
        path = Path(target)
        try:
            if path.suffix.lower() == ".pdf" or "pdf" in selected_filter.lower():
                path = controller.export_audit_pdf(path)
            else:
                path = controller.export_audit_csv(path)
        except Exception as exc:  # noqa: BLE001 - UI-Pfad muss alles abfangen
            QMessageBox.warning(
                None,
                "Audit-Export fehlgeschlagen",
                str(exc),
            )
            return
        self.showMessage(
            "Audit-Log exportiert",
            f"Gespeichert: {path}",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def _on_quit(self) -> None:
        app = QApplication.instance()
        self._host.controller.close()
        if app is not None:
            app.quit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Doppelklick oder Mittelklick → Fenster wiederherstellen.
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self._host.show_from_tray()

    # --- Headless-Hilfsfunktionen --------------------------------------------

    def menu_labels(self) -> list[str]:
        """Lese die Menü-Beschriftungen (ohne Separatoren) für Tests aus."""
        return [a.text() for a in self._menu.actions() if not a.isSeparator()]


def attach_tray_icon(host: _TrayHost, parent: QObject | None = None) -> PseudokratTrayIcon:
    """Erzeuge ein Tray-Icon und versuche es im System-Tray sichtbar zu machen.

    In headless-Umgebungen (``QT_QPA_PLATFORM=offscreen``) ist
    :func:`QSystemTrayIcon.isSystemTrayAvailable` ``False`` — das Icon wird
    dann zwar konstruiert (damit alle Slot-Verbindungen funktionieren), aber
    nicht angezeigt. Damit bleibt die Tray-Logik vollständig testbar.
    """
    tray = PseudokratTrayIcon(host, parent=parent)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    return tray
