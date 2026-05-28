"""GUI-Controller — UI-frei, damit headless testbar.

Der Controller kapselt das Öffnen/Schließen von Profilen, das Anonymisieren
und das Deanonymisieren als reine Python-API. Das Hauptfenster ruft nur diesen
Controller auf — die Geschäftslogik bleibt damit unabhängig von Qt.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pseudokrat.anonymizer import Anonymizer
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.formats import (
    FormatProcessResult,
    UnsupportedFormatError,
    handler_for,
    supported_suffixes,
)
from pseudokrat.pii.privacy_filter import load_default_detector
from pseudokrat.recognizers import (
    InvalidMandantenPatternError,
    compile_mandanten_pattern,
    recognizers_for_store,
)
from pseudokrat.store.audit_log import AuditLog
from pseudokrat.store.mapping_store import MappingStore
from pseudokrat.store.profile import MANDANTEN_PATTERN_METADATA_KEY, ProfileManager
from pseudokrat.store.secure_db import InvalidPasswordError


class GuiError(Exception):
    """Wird vom Controller in UI-freundlichen Fehlerfällen geworfen."""


@dataclass
class GuiSession:
    profile_name: str
    store: MappingStore
    audit: AuditLog
    anonymizer: Anonymizer
    deanonymizer: Deanonymizer


@dataclass(frozen=True)
class PreviewSpan:
    """Eine erkannte PII-Stelle, aufbereitet für die Vorschau-Darstellung.

    Im Gegensatz zu ``Span`` enthält dieses DTO keine Mapping-Persistenz und
    keinen Speicher-State — :meth:`GuiController.preview` ruft nur
    ``Anonymizer.detect`` auf und ändert das Mapping nicht. Wiederholte
    Aufrufe sind damit reversibel und sicher in Hotpath-UI-Updates.
    """

    start: int
    end: int
    category: str
    text: str
    score: float


@dataclass(frozen=True)
class ProfileSummary:
    """UI-freie Zusammenfassung eines Mandantenprofils (ohne Master-Passwort).

    Wird aus der unverschlüsselten ``profile_metadata`` und einem ``COUNT(*)``
    über die Mappings-Tabelle gelesen — beide Werte enthalten keinerlei
    Klartext-PII, sondern nur Zähler und Anlagedatum.
    """

    name: str
    db_path: Path
    created_utc: str
    mapping_count: int


def _read_profile_summary(name: str, db_path: Path) -> ProfileSummary:
    created = ""
    mapping_count = 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT value FROM profile_metadata WHERE key = 'created_utc' LIMIT 1"
            ).fetchone()
            if row is not None and row[0]:
                created = str(row[0])
            row2 = conn.execute("SELECT COUNT(*) FROM mappings").fetchone()
            if row2 is not None:
                mapping_count = int(row2[0])
        finally:
            conn.close()
    except sqlite3.Error:
        # DB ist beschädigt oder Schema fehlt — Summary trotzdem ausgeben.
        pass
    return ProfileSummary(
        name=name,
        db_path=db_path,
        created_utc=created,
        mapping_count=mapping_count,
    )


class GuiController:
    """Liefert den Live-Anonymisierungs-Workflow für das Hauptfenster."""

    def __init__(self, manager: ProfileManager | None = None) -> None:
        self._manager = manager or ProfileManager()
        self._session: GuiSession | None = None

    @property
    def settings(self) -> object:
        return self._manager.settings

    @property
    def session(self) -> GuiSession | None:
        return self._session

    def list_profiles(self) -> list[str]:
        return [p.name for p in self._manager.list_profiles()]

    def detect_simple_default(self) -> str | None:
        """Wrapper um :meth:`ProfileManager.detect_simple_default` — liefert
        den Profilnamen für den GUI-Simple-Mode-Pfad oder ``None``."""
        return self._manager.detect_simple_default()

    def list_profile_summaries(self) -> list[ProfileSummary]:
        """Listet alle Profile inkl. Anlage-Datum und Mapping-Anzahl auf."""
        return [
            _read_profile_summary(p.name, p.db_path) for p in self._manager.list_profiles()
        ]

    def create_profile(
        self,
        name: str,
        password: str,
        *,
        mandanten_pattern: str | None = None,
    ) -> ProfileSummary:
        """Legt ein neues Profil an, ohne die aktive Session zu ändern.

        Wirft :class:`GuiError` bei leerem Namen/Passwort oder wenn bereits
        ein Profil mit identischem Pfad existiert. Validierung der erlaubten
        Zeichen erfolgt im :class:`ProfileManager`; dessen ``ValueError``
        wird hier zu :class:`GuiError`.

        Wenn ``mandanten_pattern`` gesetzt ist, wird es in
        ``profile_metadata`` unter :data:`MANDANTEN_PATTERN_METADATA_KEY`
        abgelegt. Ein ungültiges Regex schlägt mit :class:`GuiError` fehl
        und das Profil wird nicht angelegt.
        """
        if not name.strip():
            raise GuiError("Bitte einen Profilnamen eingeben.")
        if not password:
            raise GuiError("Bitte ein Master-Passwort eingeben.")
        try:
            target = self._manager.profile_path(name)
        except ValueError as exc:
            raise GuiError(str(exc)) from exc
        if target.exists():
            raise GuiError(f"Profil '{name}' existiert bereits.")
        if mandanten_pattern is not None and mandanten_pattern != "":
            try:
                compile_mandanten_pattern(mandanten_pattern)
            except InvalidMandantenPatternError as exc:
                raise GuiError(str(exc)) from exc
        try:
            store, _audit = self._manager.open_or_create(name, password)
        except InvalidPasswordError as exc:  # pragma: no cover - neue DB kann nicht fehlschlagen
            raise GuiError(str(exc)) from exc
        if mandanten_pattern is not None and mandanten_pattern != "":
            store.set_metadata(MANDANTEN_PATTERN_METADATA_KEY, mandanten_pattern)
        store.close()
        return _read_profile_summary(name, target)

    def open_profile(self, name: str, password: str, *, disable_ml: bool = True) -> None:
        if not name.strip():
            raise GuiError("Bitte einen Profilnamen eingeben.")
        if not password:
            raise GuiError("Bitte ein Master-Passwort eingeben.")
        try:
            store, audit = self._manager.open_or_create(name, password)
        except InvalidPasswordError as exc:
            raise GuiError(str(exc)) from exc
        except ValueError as exc:
            raise GuiError(str(exc)) from exc
        self._activate_session(name, store, audit, disable_ml=disable_ml)

    def open_simple_profile(self, name: str, *, disable_ml: bool = True) -> None:
        """Öffnet ein Simple-Mode-Profil ohne Passwort-Prompt.

        Verwendet den OS-Keyring-Trust-Anchor. Wirft ``GuiError`` mit
        einer klaren Meldung, wenn das Profil im Passwort-Modus ist oder
        die Keyring-Library fehlt — ein stiller Fallback auf den
        Passwort-Dialog wäre verwirrend, weil der GUI-Simple-Mode genau
        diesen Dialog vermeiden will.
        """
        if not name.strip():
            raise GuiError("Bitte einen Profilnamen eingeben.")
        try:
            store, audit = self._manager.open_or_create_simple(name)
        except RuntimeError as exc:
            # keyring-Lib fehlt → klare Anweisung an den Nutzer.
            raise GuiError(
                "Simple-Mode benötigt die Keyring-Bibliothek. "
                "Installiere mit: pip install pseudokrat[simple-mode]"
            ) from exc
        except (InvalidPasswordError, ValueError) as exc:
            raise GuiError(str(exc)) from exc
        self._activate_session(name, store, audit, disable_ml=disable_ml)

    def _activate_session(
        self,
        name: str,
        store: MappingStore,
        audit: AuditLog,
        *,
        disable_ml: bool,
    ) -> None:
        """Gemeinsame Session-Aktivierung für Passwort- und Simple-Mode-
        Pfad. Schließt ggf. eine bestehende Session sauber, baut den
        Anonymizer/Deanonymizer und persistiert die neue Session."""
        settings = self._manager.settings
        detector = None if disable_ml or settings.disable_ml else load_default_detector(settings)
        anonymizer = Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=detector,
            audit_log=audit,
            model_version="disabled" if (disable_ml or settings.disable_ml) else settings.model_id,
        )
        deanonymizer = Deanonymizer(
            store=store,
            audit_log=audit,
            model_version="disabled" if (disable_ml or settings.disable_ml) else settings.model_id,
        )
        self.close()  # ggf. bestehende Session sauber schließen
        self._session = GuiSession(
            profile_name=name,
            store=store,
            audit=audit,
            anonymizer=anonymizer,
            deanonymizer=deanonymizer,
        )

    def close(self) -> None:
        if self._session is not None:
            self._session.store.close()
            self._session = None

    def anonymize(self, text: str) -> tuple[str, dict[str, int]]:
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        result = self._session.anonymizer.anonymize(text)
        return result.text, dict(result.entity_counts)

    def deanonymize(self, text: str) -> tuple[str, int, int]:
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        result = self._session.deanonymizer.deanonymize(text)
        return (
            result.text,
            len(result.resolved_placeholders),
            len(result.missing_placeholders),
        )

    def preview(self, text: str) -> list[PreviewSpan]:
        """Erkennt PII im Text, ohne das Mapping zu mutieren.

        Liefert die erkannten Spans als immutable :class:`PreviewSpan`-Liste in
        ``start``-Reihenfolge. Damit lässt sich der Vorschau-Editor inkl.
        farbiger Highlights und Tooltips bedienen, ohne dass jeder Hover oder
        Tastendruck neue Mapping-Einträge erzeugt.
        """
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        spans = self._session.anonymizer.detect(text)
        return [
            PreviewSpan(
                start=s.start,
                end=s.end,
                category=s.category,
                text=s.text,
                score=s.score,
            )
            for s in sorted(spans, key=lambda s: s.start)
        ]

    def verify_audit(self) -> bool:
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        return self._session.audit.verify_chain()

    def export_audit_csv(self, output_path: Path) -> Path:
        """Schreibe das Audit-Log der offenen Session als CSV an ``output_path``."""
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._session.audit.export_csv(), encoding="utf-8")
        return output_path

    def export_audit_pdf(self, output_path: Path) -> Path:
        """Schreibe das Audit-Log der offenen Session als PDF an ``output_path``."""
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        return self._session.audit.export_pdf(
            output_path, profile_name=self._session.profile_name
        )

    def supported_file_suffixes(self) -> list[str]:
        return supported_suffixes()

    def process_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        deanonymize: bool = False,
    ) -> FormatProcessResult:
        """Anonymisiere oder deanonymisiere eine strukturierte Datei.

        Wenn ``output_path`` ``None`` ist, wird ``<stem>.anon<suffix>`` bzw.
        ``<stem>.deanon<suffix>`` neben dem Original abgelegt. Die Original-
        Datei bleibt unangetastet.
        """
        if self._session is None:
            raise GuiError("Kein Profil geöffnet.")
        if not input_path.exists():
            raise GuiError(f"Datei existiert nicht: {input_path}")
        try:
            handler = handler_for(input_path)
        except UnsupportedFormatError as exc:
            raise GuiError(str(exc)) from exc

        suffix = "deanon" if deanonymize else "anon"
        target = output_path or handler.default_output_path(input_path, suffix)
        target.parent.mkdir(parents=True, exist_ok=True)

        session = self._session
        if deanonymize:
            transform = lambda t: session.deanonymizer.deanonymize(t).text  # noqa: E731
        else:
            transform = lambda t: session.anonymizer.anonymize(t).text  # noqa: E731
        return handler.process(input_path, target, transform=transform)
