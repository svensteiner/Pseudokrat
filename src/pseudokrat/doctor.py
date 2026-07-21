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
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pseudokrat.store.profile import ProfileManager

#: Stem-Prefixe der Bestandsleichen-Files aus Pre-Iter-14-Doctor-Versionen.
#: Diese landeten im echten ``profiles_dir`` mit nur-RAM-Keyring-Secret und
#: blockieren nach App-Restart den Doctor-Roundtrip. Wir räumen sie beim
#: ersten Iter-14-Doctor-Lauf einmalig auf — danach existiert keine solche
#: Datei mehr, weil die Sandbox jetzt in einem ``TemporaryDirectory`` lebt.
#:
#: Zwei Varianten, weil ``_safe_slug`` führende Underscores stript:
#: Profilname ``_doctor_smoke`` → Slug ``doctor_smoke`` → File ``doctor_smoke.sqlite``.
#: Die Underscore-Variante decken wir defensiv mit ab.
_LEGACY_SANDBOX_STEMS = ("doctor_smoke", "_doctor_smoke")


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
                '    pseudokrat init --simple --profile "Mein Konto"'
            ),
        )
    names = ", ".join(p.name for p in profiles)
    return Check(
        name="Profile",
        status=Status.OK,
        message=f"{len(profiles)} Profil(e): {names}",
    )


def _purge_legacy_sandbox_artifacts(profiles_dir: Path) -> None:
    """Räumt Bestandsleichen aus dem Pre-Iter-14-Doctor.

    Frühere Doctor-Versionen legten das Smoke-Profil ``_doctor_smoke.sqlite``
    direkt im echten ``profiles_dir`` ab, hielten das Keyring-Secret aber
    nur im RAM (:class:`InMemoryKeyringBackend`). Beim App-Restart blieb
    die Datei liegen, das Secret war weg — Folge-Doctor-Runs scheiterten
    beim Entschlüsseln. Diese Migration entfernt die Leichen einmalig.
    """
    if not profiles_dir.exists():
        return
    for path in profiles_dir.iterdir():
        if not path.is_file():
            continue
        if any(
            path.stem == stem or path.name.startswith(f"{stem}.") for stem in _LEGACY_SANDBOX_STEMS
        ):
            path.unlink(missing_ok=True)


def check_anonymize_roundtrip(manager: ProfileManager, *, profile_name: str | None = None) -> Check:
    """Smoke-Test: führt Anonymize+Deanonymize gegen einen Test-String durch.

    Ohne ``profile_name`` läuft der Test in einer **echten Sandbox** —
    eigenes ``TemporaryDirectory`` + eigener :class:`ProfileManager`. So
    landet keinerlei Artefakt im User-``profiles_dir`` und ein Folge-Run
    findet keinen alten State vor.

    Mit ``profile_name`` nutzt der Test das genannte User-Profil im
    Simple-Mode (OS-Keyring) — sinnvoll, um „funktioniert mein Mandanten-
    Profil noch?" zu beantworten.

    Pre-Iter-14-Bestandsleichen (``_doctor_smoke.sqlite`` im echten
    ``profiles_dir``) werden vor dem Test geräumt — sie waren der
    eigentliche Auslöser für die Härtung dieses Checks.
    """
    test_text = "Herr Müller (IBAN AT12 1200 0000 1234 5678) schickt eine Rechnung über 4.300 EUR."
    try:
        from pseudokrat.anonymizer import Anonymizer
        from pseudokrat.config import Settings
        from pseudokrat.deanonymizer import Deanonymizer
        from pseudokrat.pii.privacy_filter import PrivacyFilterDetector
        from pseudokrat.recognizers import recognizers_for_store
        from pseudokrat.store.key_protector import InMemoryKeyringBackend
        from pseudokrat.store.profile import ProfileManager as SandboxProfileManager
    except ImportError as exc:
        return Check(
            name="Anonymize-Roundtrip",
            status=Status.FAIL,
            message=f"Import-Fehler: {exc}",
        )

    # Defensive Migration auch hier — falls der Check standalone gerufen
    # wird (Tests, externe Aufrufer). run_doctor räumt zusätzlich ganz
    # am Anfang, damit auch check_profiles/check_profile_health keine
    # Leichen mehr sehen.
    _purge_legacy_sandbox_artifacts(manager.settings.profiles_dir)

    sandbox: tempfile.TemporaryDirectory[str] | None = None
    store = None
    try:
        if profile_name is None:
            # Echte Sandbox: eigener ProfileManager auf TempDir. Nach dem
            # finally-Block ist alles weg, inklusive SQLCipher-DB.
            sandbox = tempfile.TemporaryDirectory(prefix="pseudokrat-doctor-")
            sandbox_root = Path(sandbox.name)
            sandbox_settings = Settings(
                data_dir=sandbox_root,
                profiles_dir=sandbox_root / "profiles",
                model_cache_dir=sandbox_root / "models",
                model_id=manager.settings.model_id,
                disable_ml=True,
            )
            sandbox_settings.ensure_dirs()
            sandbox_manager = SandboxProfileManager(settings=sandbox_settings)
            store, _audit = sandbox_manager.open_or_create_simple(
                "smoke", backend=InMemoryKeyringBackend()
            )
        else:
            store, _audit = manager.open_or_create_simple(profile_name)
    except Exception as exc:  # pragma: no cover - vorsichtig
        if sandbox is not None:
            sandbox.cleanup()
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
        if sandbox is not None:
            sandbox.cleanup()

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


def check_profile_health(
    manager: ProfileManager,
    *,
    keyring_backend: object | None = None,
) -> Check:
    """Prüft, ob bestehende Simple-Mode-Profile öffenbar sind.

    Echte User-Pfade, die hier hängenbleiben:
    * Backup-Restore auf neuem Konto → OS-Keyring-Eintrag fehlt
    * Manuelle Profil-Datei-Verschiebung ohne Salt
    * Profil-DB korrumpiert

    Designentscheidungen:

    * Passwort-Modus-Profile werden **nicht** geprüft — sie verlangen das
      Master-Passwort des Nutzers, das Doctor nicht erfragt. Stattdessen
      werden sie in der OK-Meldung als „N nicht offline prüfbar" gezählt.
    * Kaputtes Simple-Mode-Profil ist **WARN, nicht FAIL** — Doctor bleibt
      nutzbar, nennt aber namentlich, welches Profil und mit welchem
      Befehl behoben werden kann. Passt zum Pilot-Tester-Mantra „eine
      klare Anlaufstelle, ein konkreter nächster Schritt".

    ``keyring_backend`` ist ein optionaler Test-Hook — Produktions-Code
    passt das nie an, der Default greift via :class:`SystemKeyringBackend`
    auf den echten OS-Keyring zu.
    """
    from pseudokrat.store.key_protector import (
        KeyringBackend,
        OsKeyringKeyProtector,
    )
    from pseudokrat.store.secure_db import profile_uses_keyring

    backend: KeyringBackend | None = None
    if keyring_backend is not None:
        if not isinstance(keyring_backend, KeyringBackend):
            raise TypeError("keyring_backend muss das KeyringBackend-Protocol implementieren.")
        backend = keyring_backend

    profiles = manager.list_profiles()
    if not profiles:
        return Check(
            name="Profile-Health",
            status=Status.WARN,
            message=(
                "Keine Profile vorhanden — überspringe Health-Check. "
                "Lege ein Profil an mit:\n"
                "    pseudokrat install"
            ),
        )

    broken: list[tuple[str, str]] = []
    healthy = 0
    password_mode_count = 0
    for profile in profiles:
        if not profile_uses_keyring(profile.db_path):
            password_mode_count += 1
            continue
        try:
            protector = OsKeyringKeyProtector(profile.name, backend=backend)
            store, _audit = manager.open_or_create(profile.name, protector=protector)
        except Exception as exc:
            broken.append((profile.name, str(exc).splitlines()[0]))
            continue
        store.close()
        healthy += 1

    if not broken:
        msg_parts = [f"{healthy} Simple-Mode-Profil(e) öffenbar"]
        if password_mode_count:
            msg_parts.append(f"{password_mode_count} Passwort-Profil(e) nicht offline prüfbar")
        return Check(
            name="Profile-Health",
            status=Status.OK,
            message=", ".join(msg_parts) + ".",
        )

    lines = [
        f"{healthy} OK, {len(broken)} nicht öffenbar:",
    ]
    for name, reason in broken:
        lines.append(f"  • {name!r}: {reason}")
    lines.append(
        "Hinweis: bei Backup-Restore oder Konto-Wechsel ist der "
        "OS-Keyring-Eintrag verloren — Profil mit\n"
        "    pseudokrat profiles remove <name>\n"
        "entfernen und neu anlegen, oder Original-Konto re-aktivieren."
    )
    return Check(
        name="Profile-Health",
        status=Status.WARN,
        message="\n".join(lines),
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
        message=(f"Installiert: {status.cache_dir} ({status.gigabytes_on_disk:.2f} GB)"),
    )


def check_pdf_stack() -> Check:
    """PyMuPDF (fitz) verfügbar? Ohne sie kann die Ordner-Lösung keine
    PDFs layout-erhaltend schwärzen."""
    for mod_name in ("pymupdf", "fitz"):
        try:
            importlib.import_module(mod_name)
        except ImportError:
            continue
        return Check(
            name="PDF-Stack",
            status=Status.OK,
            message="PyMuPDF verfügbar — PDFs werden layout-erhaltend geschwärzt.",
        )
    return Check(
        name="PDF-Stack",
        status=Status.WARN,
        message=(
            "PyMuPDF (pymupdf) nicht installiert — PDF-Anonymisierung in der "
            "Ordner-Lösung nicht möglich. Install:\n"
            "    pip install pseudokrat[watcher]"
        ),
    )


def check_ocr_stack() -> Check:
    """RapidOCR verfügbar? Nötig, um Text in Bildern/Scan-PDFs zu schwärzen."""
    try:
        importlib.import_module("rapidocr_onnxruntime")
    except ImportError:
        return Check(
            name="OCR-Stack",
            status=Status.WARN,
            message=(
                "RapidOCR nicht installiert — Text in Bildern/Scan-PDFs wird "
                "NICHT erkannt (nur einbettbarer PDF-Text). Install:\n"
                "    pip install pseudokrat[ocr]"
            ),
        )
    return Check(
        name="OCR-Stack",
        status=Status.OK,
        message="RapidOCR verfügbar — Text in Bildern/Scan-PDFs wird geschwärzt.",
    )


def check_ollama() -> Check:
    """Lokaler Ollama-Server erreichbar? Optional — die Ordner-Lösung läuft
    per Default rein regelbasiert (--no-llm). Mit Ollama werden Firmen-/
    Personen-/Markennamen zusätzlich generisch erkannt."""
    try:
        from pseudokrat.pii.ollama_detector import ollama_available
    except ImportError as exc:  # pragma: no cover - defensiv
        return Check(
            name="LLM (Ollama)",
            status=Status.WARN,
            message=f"Modul nicht importierbar: {exc}",
        )
    if ollama_available():
        return Check(
            name="LLM (Ollama)",
            status=Status.OK,
            message="Ollama erreichbar — generische Namens-Erkennung verfügbar.",
        )
    return Check(
        name="LLM (Ollama)",
        status=Status.WARN,
        message=(
            "Ollama nicht erreichbar (optional). Ohne LLM läuft die "
            "Anonymisierung regelbasiert + Begriffe.txt. Zum Aktivieren:\n"
            "    ollama serve   (und Modell laden: ollama pull mistral)"
        ),
    )


def run_doctor(manager: ProfileManager, *, profile_name: str | None = None) -> DoctorReport:
    """Führe alle Diagnose-Checks aus und liefere einen Report.

    ``profile_name`` optional: wenn gesetzt, nutzt der Roundtrip-Check
    dieses Profil statt eines Throwaway. Sinnvoll für „funktioniert mein
    Mandanten-Profil noch?".
    """
    # Bestandsleichen aus Pre-Iter-14-Doctor-Versionen ZUERST räumen —
    # sonst tauchen sie in check_profiles/check_profile_health als
    # vermeintliche User-Profile auf und verwirren den Pilot-Tester.
    _purge_legacy_sandbox_artifacts(manager.settings.profiles_dir)
    checks = (
        check_profiles(manager),
        check_profile_health(manager),
        check_anonymize_roundtrip(manager, profile_name=profile_name),
        check_pdf_stack(),
        check_ocr_stack(),
        check_ollama(),
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
        lines.append("Ergebnis: Einsatzbereit für Kern-Workflow. Optionale Komponenten warnen.")
    else:
        lines.append("Ergebnis: Vollständig einsatzbereit.")
    return "\n".join(lines)
