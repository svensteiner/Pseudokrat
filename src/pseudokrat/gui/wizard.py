"""Erstes-Start-Wizard für die Pseudokrat-GUI (§9 Megaprompt).

Begleitet den Nutzer beim allerersten Start durch drei Schritte:

1. **Willkommen** — Was ist Pseudokrat, was passiert lokal, was kostet das
   Master-Passwort wirklich (Vergessen = Mapping verloren).
2. **Profil & Master-Passwort** — Profilname, Master-Passwort mit doppelter
   Bestätigung, optionale Mandanten-Nummer als Regex.
3. **Zusammenfassung** — Bestätigung mit Profilpfad und Hinweisen zum
   weiteren Vorgehen.

Der Wizard kennt die Geschäftslogik nicht selbst — alles geht durch
:class:`GuiController.create_profile`, womit CLI- und GUI-Pfad
(``pseudokrat init``, siehe D-026) deckungsgleich bleiben.

Validierung-Architektur: Jede Wizard-Seite überschreibt
``validatePage()``. Wir benutzen bewusst **keine** automatische
``Qt.WA_DeleteOnClose``-Logik — der Aufrufer (``main_window.run``)
hält den Wizard und entscheidet nach ``exec()``-Rückgabe, ob das
Hauptfenster gezeigt werden soll.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from pseudokrat.config import Settings
from pseudokrat.gui.controller import GuiController, GuiError, ProfileSummary
from pseudokrat.pii.model_install import (
    ModelDownloadError,
    download_model,
    free_disk_bytes,
    model_status,
)

MIN_PASSWORD_LENGTH = 8


class WelcomePage(QWizardPage):
    """Erste Seite: Erklärung + Hinweis auf das Master-Passwort."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Willkommen bei Pseudokrat")
        self.setSubTitle(
            "Lokale PII-Anonymisierung für DACH-Berufsträger. "
            "Pseudokrat verlässt Ihre Maschine nicht."
        )
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Bevor Sie loslegen, legen wir ein erstes <b>Mandantenprofil</b> an. "
            "Jedes Profil hat eine eigene, mit einem <b>Master-Passwort</b> "
            "verschlüsselte Datei, in der die Zuordnung von Originaltext zu "
            "Pseudonym gespeichert wird."
            "<br/><br/>"
            "Das Master-Passwort wird <b>nicht gespeichert</b>. Vergessen Sie "
            "es, ist das Mapping nicht wiederherstellbar — das ist der Preis "
            "dafür, dass niemand sonst die Daten lesen kann."
        )
        intro.setObjectName("welcome_intro_label")
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(intro)
        layout.addStretch(1)


class ProfilePage(QWizardPage):
    """Profilname + Master-Passwort + optionales Mandanten-Pattern."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Profil anlegen")
        self.setSubTitle(
            "Wählen Sie einen Profilnamen (z. B. 'Mandant Hofer') und ein sicheres Master-Passwort."
        )

        layout = QFormLayout(self)

        self.profile_name_input = QLineEdit("Allgemein")
        self.profile_name_input.setObjectName("wizard_profile_name_input")
        layout.addRow("Profilname:", self.profile_name_input)

        self.password_input = QLineEdit()
        self.password_input.setObjectName("wizard_password_input")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Master-Passwort:", self.password_input)

        self.password_confirm_input = QLineEdit()
        self.password_confirm_input.setObjectName("wizard_password_confirm_input")
        self.password_confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Passwort wiederholen:", self.password_confirm_input)

        self.mandanten_pattern_input = QLineEdit()
        self.mandanten_pattern_input.setObjectName("wizard_mandanten_pattern_input")
        self.mandanten_pattern_input.setPlaceholderText(r"optional, z. B. M-\d{5}")
        layout.addRow("Mandantennummer-Regex (optional):", self.mandanten_pattern_input)

        hint = QLabel(
            f"Hinweis: Mindestens {MIN_PASSWORD_LENGTH} Zeichen. Verwenden Sie "
            "eine Passphrase, die Sie auch in einem Jahr noch wissen — "
            "Pseudokrat kann das Passwort nicht zurücksetzen."
        )
        hint.setWordWrap(True)
        hint.setObjectName("wizard_password_hint_label")
        layout.addRow(hint)

        # Field-Registrierung erlaubt es Tests, per ``wizard.field(...)``
        # auf die Werte zuzugreifen und sie via ``setField`` zu setzen.
        self.registerField("profile_name*", self.profile_name_input)
        self.registerField("password*", self.password_input)
        self.registerField("password_confirm*", self.password_confirm_input)
        self.registerField("mandanten_pattern", self.mandanten_pattern_input)

    # --- public api (für Tests + Wizard-Logik) -------------------------------

    @property
    def profile_name(self) -> str:
        return self.profile_name_input.text().strip()

    @property
    def password(self) -> str:
        return self.password_input.text()

    @property
    def password_confirm(self) -> str:
        return self.password_confirm_input.text()

    @property
    def mandanten_pattern(self) -> str | None:
        text = self.mandanten_pattern_input.text().strip()
        return text or None

    def validatePage(self) -> bool:  # noqa: N802 - Qt-Signatur
        wizard = self.wizard()
        assert isinstance(wizard, FirstStartWizard)
        return wizard.try_create_profile()


class SummaryPage(QWizardPage):
    """Abschluss: Bestätigung mit Profilpfad und Hinweisen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Profil angelegt")
        self.setSubTitle("Sie können jetzt mit der Anonymisierung beginnen.")
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("wizard_summary_label")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.summary_label)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 - Qt-Signatur
        wizard = self.wizard()
        assert isinstance(wizard, FirstStartWizard)
        summary = wizard.created_profile
        if summary is None:
            # Defensive: sollte nicht eintreten, ValidatePage hätte vorher geblockt.
            self.summary_label.setText(
                "<b>Kein Profil angelegt.</b> Bitte gehen Sie zurück und versuchen Sie es erneut."
            )
            return
        pattern_line = ""
        if wizard.mandanten_pattern_used:
            pattern_line = (
                f"<br/>Mandantennummer-Regex hinterlegt: "
                f"<code>{wizard.mandanten_pattern_used}</code>"
            )
        self.summary_label.setText(
            f"Profil <b>{summary.name}</b> wurde angelegt.<br/>"
            f"Datenbank: <code>{summary.db_path}</code>"
            f"{pattern_line}"
            "<br/><br/>"
            "Klicken Sie auf <b>Fertigstellen</b>, um Pseudokrat zu starten. "
            "Im Hauptfenster oben rechts geben Sie Profilname und Master-"
            "Passwort ein und öffnen das Profil per Klick auf <i>Profil öffnen</i>."
        )


class ModelDownloadPage(QWizardPage):
    """Optionale Seite: ML-Modell jetzt oder später herunterladen.

    Wird **nur eingehängt**, wenn das Modell aktuell nicht im Cache ist.
    Liegt es schon, springt der Wizard die Seite stillschweigend.
    """

    PAGE_TITLE = "ML-Modell (optional)"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(self.PAGE_TITLE)
        self.setSubTitle(
            "Pseudokrat erkennt strukturierte DACH-PII auch ohne ML-Modell. "
            "Für Personennamen und freie Adressen lädt das optionale Modell "
            "etwa 3 GB aus dem HuggingFace-Hub."
        )

        layout = QVBoxLayout(self)
        self.info_label = QLabel()
        self.info_label.setObjectName("wizard_model_info_label")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.download_checkbox = QCheckBox("Modell jetzt herunterladen")
        self.download_checkbox.setObjectName("wizard_model_download_checkbox")
        self.download_checkbox.setChecked(False)
        layout.addWidget(self.download_checkbox)

        self.status_label = QLabel()
        self.status_label.setObjectName("wizard_model_status_label")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self._download_attempted = False

    def initializePage(self) -> None:  # noqa: N802 - Qt-Signatur
        settings = Settings.load()
        free_gb = free_disk_bytes(settings.model_cache_dir) / (1024**3)
        status = model_status(settings)
        if status.is_present:
            self.info_label.setText(
                f"Modell '{settings.model_id}' ist bereits installiert "
                f"({status.gigabytes_on_disk:.2f} GB unter "
                f"{settings.model_cache_dir})."
            )
            self.download_checkbox.setEnabled(False)
            self.download_checkbox.setChecked(False)
        else:
            self.info_label.setText(
                f"Cache-Verzeichnis: <code>{settings.model_cache_dir}</code><br/>"
                f"Verfügbarer Speicherplatz: <b>{free_gb:.1f} GB</b><br/>"
                "Sie können den Download auch später über "
                "<code>pseudokrat model download --yes</code> nachholen."
            )
            self.info_label.setTextFormat(Qt.TextFormat.RichText)

    def validatePage(self) -> bool:  # noqa: N802 - Qt-Signatur
        if not self.download_checkbox.isChecked():
            return True
        if self._download_attempted:
            return True
        wizard = self.wizard()
        assert isinstance(wizard, FirstStartWizard)
        self._download_attempted = True
        return wizard.try_download_model(self.status_label)


class FirstStartWizard(QWizard):
    """Drei-Seiten-Wizard, der ein neues Profil über den GuiController anlegt.

    Tests konstruieren den Wizard direkt und navigieren die Seiten über
    ``setField()`` + ``next()`` oder rufen :meth:`try_create_profile`
    direkt auf. Eine echte ``exec()``-Schleife wird in den Tests nicht
    benötigt — die Wizard-Pages exponieren die nötigen Felder und Slots.
    """

    def __init__(
        self,
        controller: GuiController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._created: ProfileSummary | None = None
        self._mandanten_pattern_used: str | None = None

        self.setWindowTitle("Pseudokrat — Erster Start")
        self.setOption(QWizard.WizardOption.IndependentPages, False)
        self.setOption(QWizard.WizardOption.NoCancelButton, False)

        self.welcome_page = WelcomePage(self)
        self.profile_page = ProfilePage(self)
        self.model_page = ModelDownloadPage(self)
        self.summary_page = SummaryPage(self)

        self.addPage(self.welcome_page)
        self.addPage(self.profile_page)
        self.addPage(self.model_page)
        self.addPage(self.summary_page)

        # Deutsche Button-Beschriftungen.
        self.setButtonText(QWizard.WizardButton.NextButton, "Weiter")
        self.setButtonText(QWizard.WizardButton.BackButton, "Zurück")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Fertigstellen")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Abbrechen")

    @property
    def controller(self) -> GuiController:
        return self._controller

    @property
    def created_profile(self) -> ProfileSummary | None:
        return self._created

    @property
    def mandanten_pattern_used(self) -> str | None:
        return self._mandanten_pattern_used

    def try_create_profile(self) -> bool:
        """Validiere die Eingaben und versuche die Profil-Anlage.

        Wird von :meth:`ProfilePage.validatePage` aufgerufen. Bei Fehler
        zeigt eine ``QMessageBox`` die Ursache und ``False`` blockt die
        Wizard-Navigation, sodass der Nutzer korrigieren kann. Bei
        Erfolg wird das Profil im Controller-State vorgehalten.
        """
        name = self.profile_page.profile_name
        password = self.profile_page.password
        confirm = self.profile_page.password_confirm
        pattern = self.profile_page.mandanten_pattern

        if not name:
            self._warn("Bitte einen Profilnamen eingeben.")
            return False
        if len(password) < MIN_PASSWORD_LENGTH:
            self._warn(f"Master-Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.")
            return False
        if password != confirm:
            self._warn("Die beiden Passwörter stimmen nicht überein.")
            return False

        try:
            summary = self._controller.create_profile(
                name,
                password,
                mandanten_pattern=pattern,
            )
        except GuiError as exc:
            self._warn(str(exc))
            return False

        self._created = summary
        self._mandanten_pattern_used = pattern
        return True

    def _warn(self, message: str) -> None:
        """Zeigt eine Fehlermeldung; in Tests via Monkeypatching abfangbar."""
        QMessageBox.warning(self, "Profil konnte nicht angelegt werden", message)

    def try_download_model(self, status_label: QLabel) -> bool:
        """Versucht den Modell-Download. Blockt die Wizard-Nav bei Fehler nicht.

        Wir blocken die Wizard-Navigation bewusst NICHT bei Fehlschlag —
        der Nutzer kann den Download jederzeit später per CLI nachholen.
        Stattdessen aktualisieren wir das Status-Label inline.
        """
        try:
            settings = Settings.load()
            status_label.setText("Lade Modell — kann mehrere Minuten dauern …")
            QWizard.repaint(self)
            result = download_model(settings, progress=status_label.setText)
            status_label.setText(f"Erfolgreich heruntergeladen: {result.gigabytes_on_disk:.2f} GB.")
            return True
        except ModelDownloadError as exc:
            status_label.setText(
                f"Download fehlgeschlagen: {exc}\n"
                "Sie können es später jederzeit mit "
                "`pseudokrat model download --yes` nachholen."
            )
            return True  # Navigation freigeben — Wizard bleibt nutzbar


def first_start_required(controller: GuiController) -> bool:
    """True, wenn der Wizard beim App-Start gezeigt werden soll.

    Bedingung: Es gibt noch keine Profile auf der Platte. Wird vom
    Modul ``main_window`` aus :func:`run` heraus aufgerufen, um zu
    entscheiden, ob der Wizard vor dem Hauptfenster läuft.
    """
    return not controller.list_profile_summaries()
