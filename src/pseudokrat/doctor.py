"""Self-Diagnose ``pseudokrat doctor`` — Pilot-Test-Friendly.

Hintergrund (PRL Iter-8): Wenn ein Pilot-Tester sagt „läuft nicht"
brauchen wir EINE Anlaufstelle, die alle Komponenten checkt und ein
klares Ja/Nein pro Komponente liefert. Ohne `doctor` müsste der Tester
einzelne CLI-Befehle ausprobieren — das ist die Reibung, die wir
eliminieren wollen.

Liefert:

* Profile vorhanden? Welche?
* Lassen sich Profile öffnen (Keyring funktioniert)?
* Recognizer-Pipeline: läuft ein Smoke-Anonymize/Deanonymize-Roundtrip?
* Privacy-Filter-Modell: installiert?
* Hotkey-Library: importierbar?
* Optional: Windows-Registry-Status (Context-Menu, Autostart).

Jede Komponente liefert :class:`Check`-Status ``OK`` / ``WARN`` /
``FAIL`` plus Klartext-Begründung. Ein einzelnes ``FAIL`` setzt den
Exit-Code auf 1, sonst 0. ``WARN`` ist informativ, nicht-blockierend.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pseudokrat.store.profile import ProfileManager


class Status(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Check:
    """Ein einzelnes Diagnose-Ergebnis."""

    name: str
    status: Status
    message: str


@dataclass(frozen=True)
class DoctorReport:
    """Ergebnis eines vollen ``doctor``-Laufs."""

    checks: tuple[Check, ...] = field(default_factory=tuple)

    @property
    def has_failures(self) -> bool:
        return any(c.status is Status.FAIL for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status is Status.WARN for c in self.checks)

    def exit_code(self) -> int:
        return 1 if self.has_failures else 0


def check_profiles(manager: ProfileManager) -> Check:
    """Listet vorhandene Profile. Kein Profil = FAIL (Tester braucht
    mindestens das Default-Profil, das ``pseudokrat install`` anlegt)."""
    try:
        profiles = list(manager.list_profiles())
    except Exception as exc:  # pragma: no cover - vorsichtig
        return Check(
            name="Profile",
            status=Status.FAIL,
            message=f"Konnte Profile nicht auflisten: {exc}",
        )
    if not profiles:
        return Check(
            name="Profile",
            status=Status.FAIL,
            message=(
                "Kein Profil vorhanden. Lege eines an mit:\n"
                "    pseudokrat install\n"
                "  oder manuell:\n"
                "    pseudokrat init --simple --profile \"Mein Konto\""
            ),
        )
    names = ", ".join(p.name for p in profiles)
    return Check(
        name="Profile",
        status=Status.OK,
        message=f"{len(profiles)} Profil(e): {names}",
    )


def check_anonymize_roundtrip(
    manager: ProfileManager, *, profile_name: str | None = None
) -> Check:
    """Smoke-Test: legt ein temporäres Profil an (falls keines vorhanden)
    und führt Anonymize+Deanonymize gegen einen Test-String durch."""
    test_text = (
        "Herr Müller (IBAN AT12 1200 0000 1234 5678) "
        "schickt eine Rechnung über 4.300 EUR."
    )
    try:
        from pseudokrat.anonymizer import Anonymizer
        from pseudokrat.deanonymizer import Deanonymizer
        from pseudokrat.pii.privacy_filter import PrivacyFilterDetector
        from pseudokrat.recognizers import recognizers_for_store
        from pseudokrat.store.key_protector import InMemoryKeyringBackend
    except ImportError as exc:
        return Check(
            name="Anonymize-Roundtrip",
            status=Status.FAIL,
            message=f"Import-Fehler: {exc}",
        )

    try:
        if profile_name is None:
            # Eigenes Throwaway-Profil — InMemoryKeyringBackend
            # verhindert OS-Keyring-Verschmutzung.
            store, _audit = manager.open_or_create_simple(
                "_doctor_smoke",
                backend=InMemoryKeyringBackend(),
            )
        else:
            store, _audit = manager.open_or_create_simple(profile_name)
    except Exception as exc:  # pragma: no cover - vorsichtig
        return Check(
            name="Anonymize-Roundtrip",
            status=Status.FAIL,
            message=f"Profil konnte nicht geöffnet werden: {exc}",
        )

    try:
        # PrivacyFilterDetector kann ohne Modell auskommen (Stub bei
        # PSEUDOKRAT_DISABLE_ML=1). Doctor schaltet ihn bewusst aus —
        # wir messen Recognizer-Pipeline, nicht ML.
        detector: PrivacyFilterDetector | None = None
        anon = Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=detector,
        )
        deanon = Deanonymizer(store=store)
        anonymized = anon.anonymize(test_text)
        recovered = deanon.deanonymize(anonymized.text)
    except Exception as exc:
        return Check(
            name="Anonymize-Roundtrip",
            status=Status.FAIL,
            message=f"Pipeline-Fehler: {exc}",
        )
    finally:
        store.close()

    if recovered.text != test_text:
        return Check(
            name="Anonymize-Roundtrip",
            status=Status.FAIL,
            message=(
                "Deanonymisierung lieferte nicht den Originaltext zurück. "
                "Das ist ein KRITISCHER Pipeline-Bug. Bitte melden."
            ),
        )

    entities = sum(anonymized.entity_counts.values())
    return Check(
        name="Anonymize-Roundtrip",
        status=Status.OK,
        message=f"Roundtrip OK ({entities} Entitäten erkannt + 1:1 wiederhergestellt)",
    )


def check_hotkey_backend() -> Check:
    """Hotkey-Library importierbar? Auf Windows: ``keyboard``,
    macOS/Linux: ``pynput``."""
    candidates = ("keyboard", "pynput")
    available = []
    for mod_name in candidates:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            continue
        available.append(mod_name)
    if not available:
        return Check(
            name="Hotkey-Backend",
            status=Status.WARN,
            message=(
                "Weder 'keyboard' noch 'pynput' installiert — "
                "Hotkeys funktionieren nicht. Install:\n"
                "    pip install pseudokrat[hotkeys]"
            ),
        )
    return Check(
        name="Hotkey-Backend",
        status=Status.OK,
        message=f"Backend(s) verfügbar: {', '.join(available)}",
    )


def check_ml_model() -> Check:
    """Privacy-Filter-Modell installiert? Nur informativ — Recognizer-
    Pipeline läuft auch ohne ML."""
    try:
        from pseudokrat.pii.model_install import model_status
    except ImportError as exc:
        return Check(
            name="ML-Modell",
            status=Status.WARN,
            message=f"Modul nicht importierbar: {exc}",
        )
    try:
        status = model_status()
    except Exception as exc:  # pragma: no cover - vorsichtig
        return Check(
            name="ML-Modell",
            status=Status.WARN,
            message=f"Status nicht lesbar: {exc}",
        )
    if not status.is_present:
        return Check(
            name="ML-Modell",
            status=Status.WARN,
            message=(
                "Privacy-Filter-Modell nicht installiert. "
                "DACH-Recognizer arbeiten weiter; ML-Augmentation für "
                "freie Texte fehlt. Install:\n"
                "    pseudokrat model download"
            ),
        )
    return Check(
        name="ML-Modell",
        status=Status.OK,
        message=(
            f"Installiert: {status.cache_dir} "
            f"({status.gigabytes_on_disk:.2f} GB)"
        ),
    )


def run_doctor(
    manager: ProfileManager, *, profile_name: str | None = None
) -> DoctorReport:
    """Führe alle Diagnose-Checks aus und liefere einen Report.

    ``profile_name`` optional: wenn gesetzt, nutzt der Roundtrip-Check
    dieses Profil statt eines Throwaway. Sinnvoll für „funktioniert mein
    Mandanten-Profil noch?".
    """
    checks = (
        check_profiles(manager),
        check_anonymize_roundtrip(manager, profile_name=profile_name),
        check_hotkey_backend(),
        check_ml_model(),
    )
    return DoctorReport(checks=checks)


def format_report(report: DoctorReport) -> str:
    """Plain-Text-Rendering — eine Zeile pro Check, mit Statussymbol."""
    icon = {
        Status.OK: "✓",
        Status.WARN: "⚠",
        Status.FAIL: "✗",
    }
    lines = ["Pseudokrat — Selbst-Diagnose", ""]
    for c in report.checks:
        head = f"{icon[c.status]} {c.name}: {c.status.value}"
        lines.append(head)
        for msg_line in c.message.splitlines():
            lines.append(f"    {msg_line}")
    lines.append("")
    if report.has_failures:
        lines.append("Ergebnis: NICHT EINSATZBEREIT — bitte FAIL-Punkte oben beheben.")
    elif report.has_warnings:
        lines.append(
            "Ergebnis: Einsatzbereit für Kern-Workflow. Optionale Komponenten warnen."
        )
    else:
        lines.append("Ergebnis: Vollständig einsatzbereit.")
    return "\n".join(lines)
