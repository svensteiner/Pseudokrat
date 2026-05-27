"""Pseudokrat CLI — Phase 1."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pseudokrat import __version__
from pseudokrat.anonymizer import Anonymizer
from pseudokrat.clipboard import ClipboardUnavailableError, default_clipboard
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.formats import (
    UnsupportedFormatError,
    handler_for,
)
from pseudokrat.logging_config import configure_logging
from pseudokrat.pii.privacy_filter import load_default_detector
from pseudokrat.recognizers import (
    InvalidMandantenPatternError,
    compile_mandanten_pattern,
    recognizers_for_store,
)
from pseudokrat.store.profile import MANDANTEN_PATTERN_METADATA_KEY, ProfileManager
from pseudokrat.store.secure_db import InvalidPasswordError

DEFAULT_PROFILE = "default"
MIN_PASSWORD_LENGTH = 8


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pseudokrat",
        description="Lokale PII-Anonymisierung für DACH-Berufsträger.",
    )
    parser.add_argument("--version", action="version", version=f"pseudokrat {__version__}")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log-Level (Standard: INFO).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Mandantenprofil (Standard: default).",
    )
    common.add_argument(
        "--password",
        default=None,
        help="Master-Passwort (interaktiv abfragen, wenn nicht angegeben).",
    )

    # anonymize
    p_anon = sub.add_parser("anonymize", parents=[common], help="Text anonymisieren.")
    src = p_anon.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", type=Path, help="Eingabedatei.")
    src.add_argument("--text", "-t", help="Eingabetext direkt.")
    src.add_argument("--stdin", action="store_true", help="Eingabe von stdin lesen.")
    p_anon.add_argument("--output", "-o", type=Path, help="Ausgabedatei.")
    p_anon.add_argument(
        "--no-ml", action="store_true", help="ML-Detektor überspringen (nur Recognizer)."
    )
    p_anon.add_argument(
        "--dp-amounts",
        action="store_true",
        help=(
            "Nur XLSX: numerische Spalten rangbewahrend permutieren — "
            "Summen/Mittelwerte bleiben gleich, Zuordnung Mandant→Betrag "
            "wird zufällig durchgemischt (siehe DECISIONS D-032)."
        ),
    )

    # deanonymize
    p_deanon = sub.add_parser(
        "deanonymize", parents=[common], help="Anonymisierten Text zurückverwandeln."
    )
    src = p_deanon.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", "-i", type=Path, help="Eingabedatei.")
    src.add_argument("--text", "-t", help="Eingabetext direkt.")
    src.add_argument("--stdin", action="store_true", help="Eingabe von stdin lesen.")
    p_deanon.add_argument("--output", "-o", type=Path, help="Ausgabedatei.")

    # clipboard
    p_clip = sub.add_parser(
        "clipboard",
        parents=[common],
        help="Zwischenablage anonymisieren oder deanonymisieren (Hotkey-Workflow).",
    )
    p_clip_sub = p_clip.add_subparsers(dest="subcommand", required=True)
    p_clip_anon = p_clip_sub.add_parser(
        "anonymize",
        help="Inhalt der Zwischenablage anonymisieren und zurückschreiben.",
    )
    p_clip_anon.add_argument(
        "--no-ml", action="store_true", help="ML-Detektor überspringen (nur Recognizer)."
    )
    p_clip_sub.add_parser(
        "deanonymize",
        help="Inhalt der Zwischenablage deanonymisieren und zurückschreiben.",
    )

    # init — Erstes-Start-Wizard für CLI-Nutzer (§9 Megaprompt)
    p_init = sub.add_parser(
        "init",
        help="Mandantenprofil neu anlegen (Master-Passwort setzen).",
    )
    p_init.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Name des neuen Mandantenprofils (Standard: default).",
    )
    p_init.add_argument(
        "--password",
        default=None,
        help="Master-Passwort (interaktiv abfragen, wenn nicht angegeben).",
    )
    p_init.add_argument(
        "--simple",
        action="store_true",
        help=(
            "Simple-Mode: kein Master-Passwort — Schlüssel wird im OS-Keyring "
            "(Windows Credential Manager / macOS Keychain) abgelegt und ist an "
            "das Windows-/macOS-Konto gebunden. Bequemer Default für "
            "Einzelplatz-Nutzer. Power-User / strenge Compliance: ohne --simple."
        ),
    )
    p_init.add_argument(
        "--mandanten-pattern",
        default=None,
        help=(
            "Optional: Regex für die kanzlei-/profilspezifische Mandantennummer "
            "(z. B. 'M-\\d{5}'). Wird in profile_metadata gespeichert und beim "
            "Anonymisieren automatisch geladen."
        ),
    )

    # profile list / set-mandanten-pattern / show-mandanten-pattern
    p_prof = sub.add_parser("profiles", help="Profile verwalten.")
    p_prof_sub = p_prof.add_subparsers(dest="subcommand", required=True)
    p_prof_sub.add_parser("list", help="Vorhandene Profile auflisten.")

    p_set_pat = p_prof_sub.add_parser(
        "set-mandanten-pattern",
        help="Mandantennummer-Regex für ein bestehendes Profil setzen oder ändern.",
    )
    p_set_pat.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Mandantenprofil (Standard: default).",
    )
    p_set_pat.add_argument(
        "--pattern",
        default=None,
        help="Regex-Pattern (leer = Eintrag löschen). Wird auf Kompilierbarkeit geprüft.",
    )
    p_set_pat.add_argument(
        "--clear",
        action="store_true",
        help="Vorhandenes Mandanten-Pattern entfernen.",
    )
    p_set_pat.add_argument(
        "--password",
        default=None,
        help="Master-Passwort (interaktiv abfragen, wenn nicht angegeben).",
    )

    p_show_pat = p_prof_sub.add_parser(
        "show-mandanten-pattern",
        help="Aktuelles Mandantennummer-Regex eines Profils ausgeben (ohne Passwort).",
    )
    p_show_pat.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Mandantenprofil (Standard: default).",
    )

    # server
    p_srv = sub.add_parser(
        "server",
        parents=[common],
        help=(
            "Lokalen HTTP-Server für Office-Add-ins starten (127.0.0.1). "
            "Status: Scaffold — siehe addins/excel/README.md."
        ),
    )
    p_srv_sub = p_srv.add_subparsers(dest="subcommand", required=True)
    p_srv_start = p_srv_sub.add_parser("start", help="Server im Vordergrund starten.")
    p_srv_start.add_argument(
        "--host", default="127.0.0.1", help="Bind-Adresse (Default: 127.0.0.1)."
    )
    p_srv_start.add_argument(
        "--port", type=int, default=31337, help="Port (Default: 31337)."
    )
    p_srv_start.add_argument(
        "--no-ml", action="store_true", help="ML-Detektor überspringen."
    )
    p_srv_sub.add_parser(
        "token",
        help="Aktuellen Bearer-Token anzeigen (Pfad + Inhalt).",
    )

    # hotkey-daemon
    p_hk = sub.add_parser(
        "hotkey-daemon",
        parents=[common],
        help=(
            "Globalen Hotkey-Listener starten (Strg+Shift+A / Strg+Shift+D). "
            "Benötigt pseudokrat[hotkeys]. Default-Pfad bleibt OS-Hotkey-Tool — "
            "siehe DECISIONS D-024."
        ),
    )
    p_hk.add_argument(
        "--anonymize-hotkey",
        default="ctrl+shift+a",
        help="Hotkey für Anonymisierung (Default: ctrl+shift+a).",
    )
    p_hk.add_argument(
        "--deanonymize-hotkey",
        default="ctrl+shift+d",
        help="Hotkey für Deanonymisierung (Default: ctrl+shift+d).",
    )
    p_hk.add_argument(
        "--no-ml", action="store_true", help="ML-Detektor überspringen."
    )

    # model
    p_model = sub.add_parser("model", help="ML-Modell-Verwaltung (Privacy-Filter).")
    p_model_sub = p_model.add_subparsers(dest="subcommand", required=True)
    p_model_sub.add_parser(
        "status",
        help="Anzeige, ob das Modell lokal vorhanden ist.",
    )
    p_model_download = p_model_sub.add_parser(
        "download",
        help="Modell von HuggingFace in den lokalen Cache laden (≈ 3 GB).",
    )
    p_model_download.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Bestätigt den Download ohne weitere Rückfrage.",
    )
    p_model_sub.add_parser(
        "remove",
        help="Modell-Cache entfernen (Speicherplatz freigeben).",
    )

    # audit
    p_audit = sub.add_parser("audit", parents=[common], help="Audit-Log-Operationen.")
    p_audit_sub = p_audit.add_subparsers(dest="subcommand", required=True)
    p_audit_sub.add_parser("verify", help="Hash-Kette validieren.")
    p_audit_export = p_audit_sub.add_parser("export", help="Audit-Log exportieren.")
    p_audit_export.add_argument(
        "--output", "-o", type=Path, help="Ausgabedatei (default stdout für CSV)."
    )
    p_audit_export.add_argument(
        "--format",
        "-f",
        choices=["csv", "pdf"],
        default="csv",
        help="Exportformat (Standard: csv).",
    )

    return parser


def _resolve_password(arg: str | None) -> str:
    if arg is not None:
        return arg
    env = os.environ.get("PSEUDOKRAT_PASSWORD")
    if env:
        return env
    return getpass.getpass("Master-Passwort: ")


def _open_profile(
    manager: ProfileManager,
    profile_name: str,
    password_arg: str | None,
) -> tuple[Any, Any]:
    """Single entry point für CLI-Commands, die ein bestehendes Profil
    öffnen wollen.

    Erkennt Simple-Mode-Profile (Sidecar ``<db>.keyring``) und überspringt
    in dem Fall den Passwort-Prompt. Bei klassischen Passwort-Profilen
    verhält es sich wie ein direkter ``_resolve_password`` +
    ``manager.open_or_create``-Aufruf.
    """
    from pseudokrat.store.secure_db import profile_uses_keyring

    try:
        path = manager.profile_path(profile_name)
    except ValueError:
        # Ungültiger Name → klassischer Pfad wird die Fehlermeldung liefern.
        password = _resolve_password(password_arg)
        return manager.open_or_create(profile_name, password)

    if path.exists() and profile_uses_keyring(path):
        # Simple-Mode: kein Prompt nötig, Protector wird automatisch
        # aus dem Sidecar-Marker resolved.
        return manager.open_or_create(profile_name)

    password = _resolve_password(password_arg)
    return manager.open_or_create(profile_name, password)


def _read_input(args: argparse.Namespace) -> str:
    if getattr(args, "stdin", False):
        return sys.stdin.read()
    text_arg = getattr(args, "text", None)
    if text_arg is not None:
        return str(text_arg)
    path: Path = args.input
    return path.read_text(encoding="utf-8")


def _write_output(args: argparse.Namespace, text: str) -> None:
    out: Path | None = getattr(args, "output", None)
    if out is None:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def _has_handler(path: Path | None) -> bool:
    """Alle Dateieingaben mit registriertem Format-Handler laufen über die Pipeline.

    Dadurch landet das Anonymisat IMMER neben dem Original (z. B. ``memo.anon.txt``)
    statt auf stdout — konsistent über TXT, CSV, DOCX, XLSX hinweg. Auf stdout
    geht nur, was per ``--text`` oder ``--stdin`` reinkam.
    """
    if path is None:
        return False
    try:
        handler_for(path)
    except UnsupportedFormatError:
        return False
    return True


def _cmd_anonymize(args: argparse.Namespace, manager: ProfileManager) -> int:
    try:
        store, audit = _open_profile(manager, args.profile, args.password)
    except InvalidPasswordError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    with store:
        settings = manager.settings
        detector = None if args.no_ml else load_default_detector(settings)
        anonymizer = Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=detector,
            audit_log=audit,
            model_version=settings.model_id if not settings.disable_ml else "disabled",
        )
        input_path: Path | None = getattr(args, "input", None)
        if _has_handler(input_path):
            assert input_path is not None
            try:
                handler = handler_for(input_path)
            except UnsupportedFormatError as exc:
                print(f"Fehler: {exc}", file=sys.stderr)
                return 5
            output_path: Path = (
                args.output
                if args.output is not None
                else handler.default_output_path(input_path, "anon")
            )
            handler_kwargs: dict[str, object] = {}
            dp_amounts = bool(getattr(args, "dp_amounts", False))
            if dp_amounts and handler.name == "xlsx":
                from pseudokrat.dp import permutation_key_from_secret

                handler_kwargs["permute_numeric_columns_with"] = (
                    permutation_key_from_secret(store.keys.hmac_key)
                )
            elif dp_amounts:
                print(
                    f"Hinweis: --dp-amounts hat für '{handler.name}' keine Wirkung — "
                    "nur XLSX-Beträge werden permutiert.",
                    file=sys.stderr,
                )
            result = handler.process(
                input_path,
                output_path,
                transform=lambda t: anonymizer.anonymize(t).text,
                **handler_kwargs,
            )
            print(
                f"[anonymized:{handler.name}] {result.segments_processed} Segmente "
                f"verarbeitet, {result.segments_skipped} übersprungen → {result.output_path}",
                file=sys.stderr,
            )
            return 0

        text = _read_input(args)
        result_obj = anonymizer.anonymize(text)
        _write_output(args, result_obj.text)
        print(
            f"[anonymized] {sum(result_obj.entity_counts.values())} Entitäten erkannt: "
            f"{result_obj.entity_counts}",
            file=sys.stderr,
        )
    return 0


def _cmd_deanonymize(args: argparse.Namespace, manager: ProfileManager) -> int:
    try:
        store, audit = _open_profile(manager, args.profile, args.password)
    except InvalidPasswordError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    with store:
        settings = manager.settings
        deanonymizer = Deanonymizer(
            store=store,
            audit_log=audit,
            model_version=settings.model_id if not settings.disable_ml else "disabled",
        )
        input_path: Path | None = getattr(args, "input", None)
        if _has_handler(input_path):
            assert input_path is not None
            try:
                handler = handler_for(input_path)
            except UnsupportedFormatError as exc:
                print(f"Fehler: {exc}", file=sys.stderr)
                return 5
            output_path: Path = (
                args.output
                if args.output is not None
                else handler.default_output_path(input_path, "deanon")
            )
            result_struct = handler.process(
                input_path,
                output_path,
                transform=lambda t: deanonymizer.deanonymize(t).text,
            )
            print(
                f"[deanonymized:{handler.name}] {result_struct.segments_processed} Segmente "
                f"verarbeitet → {result_struct.output_path}",
                file=sys.stderr,
            )
            return 0

        text = _read_input(args)
        result_obj = deanonymizer.deanonymize(text)
        _write_output(args, result_obj.text)
        print(
            f"[deanonymized] {len(result_obj.resolved_placeholders)} Platzhalter aufgelöst, "
            f"{len(result_obj.missing_placeholders)} unbekannt",
            file=sys.stderr,
        )
        if result_obj.missing_placeholders:
            return 3
    return 0


def _prompt_new_password() -> str | None:
    """Interaktive Passwort-Abfrage mit Bestätigung. Gibt None bei Mismatch zurück."""
    first = getpass.getpass("Neues Master-Passwort: ")
    second = getpass.getpass("Master-Passwort wiederholen: ")
    if first != second:
        return None
    return first


def _resolve_new_password(arg: str | None) -> tuple[str | None, str | None]:
    """Auflösung des Passworts für ``init`` mit doppelter Bestätigung.

    Rückgabe: (password, error_message). Genau eines davon ist None.
    """
    if arg is not None:
        return arg, None
    env = os.environ.get("PSEUDOKRAT_PASSWORD")
    if env:
        return env, None
    pw = _prompt_new_password()
    if pw is None:
        return None, "Die beiden Passwörter stimmen nicht überein."
    return pw, None


def _cmd_init(args: argparse.Namespace, manager: ProfileManager) -> int:
    """Erstes-Start-Wizard (§9 Megaprompt): legt ein neues Profil an.

    - Verweigert die Anlage, wenn bereits eine Profil-Datei existiert
      (Exit-Code 9), damit ein bestehendes Mapping nicht überschrieben wird.
    - Verlangt ein Master-Passwort von mindestens MIN_PASSWORD_LENGTH Zeichen
      (Exit-Code 10).
    - Akzeptiert das Passwort entweder per ``--password``-Flag, per
      ``PSEUDOKRAT_PASSWORD``-Env oder interaktiv mit doppelter Bestätigung.
    """
    try:
        path = manager.profile_path(args.profile)
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 11
    if path.exists():
        print(
            f"Fehler: Profil '{args.profile}' existiert bereits unter {path}. "
            "Verwenden Sie einen anderen Namen oder löschen Sie die Datei manuell.",
            file=sys.stderr,
        )
        return 9

    simple_mode = bool(getattr(args, "simple", False))
    password: str | None = None
    if simple_mode:
        if args.password is not None:
            print(
                "Fehler: --simple und --password schließen sich aus.",
                file=sys.stderr,
            )
            return 10
    else:
        resolved, err = _resolve_new_password(args.password)
        if err is not None or resolved is None:
            print(
                f"Fehler: {err or 'Passwort konnte nicht ermittelt werden.'}",
                file=sys.stderr,
            )
            return 10
        if len(resolved) < MIN_PASSWORD_LENGTH:
            print(
                f"Fehler: Master-Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.",
                file=sys.stderr,
            )
            return 10
        password = resolved

    mandanten_pattern = getattr(args, "mandanten_pattern", None)
    if mandanten_pattern is not None:
        try:
            compile_mandanten_pattern(mandanten_pattern)
        except InvalidMandantenPatternError as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 12

    try:
        if simple_mode:
            store, _audit = manager.open_or_create_simple(args.profile)
        else:
            store, _audit = manager.open_or_create(args.profile, password)
    except InvalidPasswordError as exc:  # pragma: no cover — neuer Pfad
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        # Tritt z. B. auf, wenn ``keyring`` nicht installiert ist.
        print(f"Fehler: {exc}", file=sys.stderr)
        return 13
    if mandanten_pattern is not None:
        store.set_metadata(MANDANTEN_PATTERN_METADATA_KEY, mandanten_pattern)
    store.close()

    print(f"Profil '{args.profile}' angelegt unter {path}.")
    if mandanten_pattern is not None:
        print(f"Mandanten-Pattern hinterlegt: {mandanten_pattern}")
    print("Nächste Schritte:")
    if simple_mode:
        print(
            f"  pseudokrat anonymize --profile \"{args.profile}\" "
            '--text "Mein Mandant Hofer Bau GmbH ..."'
        )
        print(
            "Hinweis: Simple-Mode — kein Master-Passwort. Der Schlüssel ist im "
            "OS-Keyring an Ihr Benutzerkonto gebunden. Bei Konto-Wechsel oder "
            "OS-Reinstall ist das Profil nicht mehr entschlüsselbar."
        )
    else:
        print(
            f"  pseudokrat anonymize --profile \"{args.profile}\" "
            '--text "Mein Mandant Hofer Bau GmbH ..."'
        )
        print("  pseudokrat profiles list")
        print(
            "Hinweis: Bewahren Sie Ihr Master-Passwort sicher auf — ohne dieses "
            "ist das Mapping nicht wiederherstellbar."
        )
    return 0


def _cmd_profiles(args: argparse.Namespace, manager: ProfileManager) -> int:
    sub = getattr(args, "subcommand", "list")
    if sub in (None, "list"):
        profiles = manager.list_profiles()
        if not profiles:
            print("Noch keine Profile angelegt.")
            return 0
        for prof in profiles:
            print(f"{prof.name}\t{prof.db_path}")
        return 0
    if sub == "show-mandanten-pattern":
        return _cmd_profile_show_pattern(args, manager)
    if sub == "set-mandanten-pattern":
        return _cmd_profile_set_pattern(args, manager)
    print(f"Fehler: Unbekanntes profiles-Subkommando '{sub}'", file=sys.stderr)
    return 1


def _cmd_profile_show_pattern(args: argparse.Namespace, manager: ProfileManager) -> int:
    """Zeigt das aktuelle Mandanten-Pattern eines Profils — ohne Master-Passwort."""
    from pseudokrat.store.profile import read_profile_metadata

    try:
        path = manager.profile_path(args.profile)
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 11
    if not path.exists():
        print(f"Fehler: Profil '{args.profile}' existiert nicht.", file=sys.stderr)
        return 13
    pattern = read_profile_metadata(path, MANDANTEN_PATTERN_METADATA_KEY)
    if pattern is None or pattern == "":
        print("(kein Mandanten-Pattern hinterlegt)")
        return 0
    print(pattern)
    return 0


def _cmd_profile_set_pattern(args: argparse.Namespace, manager: ProfileManager) -> int:
    """Setzt oder entfernt das Mandanten-Pattern eines bestehenden Profils.

    Erfordert das Master-Passwort, weil das Profil regulär geöffnet wird —
    damit ist sichergestellt, dass nur ein berechtigter Nutzer die
    Recognizer-Konfiguration eines Mandanten ändern kann.
    """
    if args.clear and args.pattern is not None:
        print(
            "Fehler: --clear und --pattern können nicht gleichzeitig angegeben werden.",
            file=sys.stderr,
        )
        return 14
    if not args.clear and args.pattern is None:
        print("Fehler: Entweder --pattern oder --clear angeben.", file=sys.stderr)
        return 14

    try:
        path = manager.profile_path(args.profile)
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 11
    if not path.exists():
        print(f"Fehler: Profil '{args.profile}' existiert nicht.", file=sys.stderr)
        return 13

    if args.pattern is not None:
        try:
            compile_mandanten_pattern(args.pattern)
        except InvalidMandantenPatternError as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 12

    try:
        store, _audit = _open_profile(manager, args.profile, getattr(args, "password", None))
    except InvalidPasswordError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    with store:
        if args.clear:
            store.delete_metadata(MANDANTEN_PATTERN_METADATA_KEY)
            print(f"Mandanten-Pattern für Profil '{args.profile}' entfernt.")
        else:
            assert args.pattern is not None
            store.set_metadata(MANDANTEN_PATTERN_METADATA_KEY, args.pattern)
            print(f"Mandanten-Pattern für Profil '{args.profile}' gesetzt: {args.pattern}")
    return 0


def _cmd_clipboard(args: argparse.Namespace, manager: ProfileManager) -> int:
    """Workflow A aus §3 des Megaprompts: Zwischenablage rein → anonymisiert raus.

    Der Befehl ist als headless-Hotkey-Ziel gedacht — der Nutzer bindet ihn
    über sein OS-Hotkey-Werkzeug (PowerToys, AutoHotkey, macOS Shortcuts)
    auf eine Tastenkombination. So bleibt die App ohne globalen Tastatur-
    Listener auskommen.
    """
    try:
        clipboard = default_clipboard()
    except ClipboardUnavailableError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 7

    try:
        text_in = clipboard.read()
    except ClipboardUnavailableError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 7

    if not text_in:
        print("Hinweis: Zwischenablage ist leer — nichts zu tun.", file=sys.stderr)
        return 8

    try:
        store, audit = _open_profile(manager, args.profile, args.password)
    except InvalidPasswordError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    with store:
        settings = manager.settings
        if args.subcommand == "anonymize":
            no_ml = getattr(args, "no_ml", False)
            detector = None if no_ml else load_default_detector(settings)
            anonymizer = Anonymizer(
                store=store,
                recognizers=recognizers_for_store(store),
                detector=detector,
                audit_log=audit,
                model_version=settings.model_id if not settings.disable_ml else "disabled",
            )
            result = anonymizer.anonymize(text_in)
            try:
                clipboard.write(result.text)
            except ClipboardUnavailableError as exc:
                print(f"Fehler: {exc}", file=sys.stderr)
                return 7
            total = sum(result.entity_counts.values())
            print(
                f"[clipboard:anonymize] Profil '{args.profile}' — "
                f"{total} Entitäten ersetzt: {result.entity_counts}",
                file=sys.stderr,
            )
            return 0

        if args.subcommand == "deanonymize":
            deanonymizer = Deanonymizer(
                store=store,
                audit_log=audit,
                model_version=settings.model_id if not settings.disable_ml else "disabled",
            )
            deanon_result = deanonymizer.deanonymize(text_in)
            try:
                clipboard.write(deanon_result.text)
            except ClipboardUnavailableError as exc:
                print(f"Fehler: {exc}", file=sys.stderr)
                return 7
            resolved = len(deanon_result.resolved_placeholders)
            missing = len(deanon_result.missing_placeholders)
            print(
                f"[clipboard:deanonymize] Profil '{args.profile}' — "
                f"{resolved} Platzhalter aufgelöst, {missing} unbekannt",
                file=sys.stderr,
            )
            if missing:
                return 3
            return 0

    return 1


def _cmd_server(args: argparse.Namespace, manager: ProfileManager) -> int:
    """Lokal-HTTP-Server-Subkommando.

    Exit-Codes:
    * 18 — Port belegt / Socket-Bind fehlgeschlagen.
    """
    from pseudokrat.server import ServerState, TokenStore, start_server

    sub = getattr(args, "subcommand", None)
    token_path = manager.settings.data_dir / "server_token.txt"

    if sub == "token":
        store = TokenStore(token_path)
        token = store.ensure()
        print(f"Token-Pfad: {token_path}")
        print(f"Token: {token}")
        return 0

    if sub == "start":
        password = _resolve_password(args.password)
        state = ServerState(
            profile_manager=manager,
            profile_name=args.profile,
            password=password,
            token_store=TokenStore(token_path),
            no_ml=bool(getattr(args, "no_ml", False)),
        )
        # Schneller Auth-Check: einmal öffnen, dann sofort schließen.
        try:
            anonymizer, _ = state.open_session()
            del anonymizer
            state.close()
        except InvalidPasswordError as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 2

        token = state.token_store.ensure()
        try:
            running = start_server(
                state,
                host=args.host,
                port=args.port,
                in_background=False,
            )
        except OSError as exc:
            print(f"Fehler: Server konnte nicht binden ({exc}).", file=sys.stderr)
            return 18

        print(
            f"Pseudokrat-Server läuft auf http://{args.host}:{args.port} "
            f"(Profil '{args.profile}'). Bearer-Token: {token}\n"
            "Strg+C zum Beenden.",
            file=sys.stderr,
        )
        try:
            running.httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer wird gestoppt …", file=sys.stderr)
        finally:
            running.httpd.server_close()
        return 0

    print(f"Fehler: Unbekanntes server-Subkommando '{sub}'", file=sys.stderr)
    return 1


def _cmd_hotkey_daemon(args: argparse.Namespace, manager: ProfileManager) -> int:
    """Startet den globalen Hotkey-Daemon im Vordergrund.

    Exit-Codes:
    * 17 — Hotkey-Backend nicht verfügbar (Library nicht installiert
      oder Berechtigungen fehlen).
    """
    from pseudokrat.hotkey import (
        HotkeyConfig,
        HotkeyDaemon,
        HotkeyUnavailableError,
    )

    try:
        store, audit = _open_profile(manager, args.profile, args.password)
    except InvalidPasswordError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    settings = manager.settings
    no_ml = bool(getattr(args, "no_ml", False))
    detector = None if no_ml else load_default_detector(settings)
    anonymizer = Anonymizer(
        store=store,
        recognizers=recognizers_for_store(store),
        detector=detector,
        audit_log=audit,
        model_version=settings.model_id if not settings.disable_ml else "disabled",
    )
    deanonymizer = Deanonymizer(
        store=store,
        audit_log=audit,
        model_version=settings.model_id if not settings.disable_ml else "disabled",
    )

    try:
        clipboard = default_clipboard()
    except ClipboardUnavailableError as exc:
        store.close()
        print(f"Fehler: {exc}", file=sys.stderr)
        return 7

    def _do_anonymize() -> None:
        try:
            text = clipboard.read()
        except ClipboardUnavailableError:
            return
        if not text:
            return
        clipboard.write(anonymizer.anonymize(text).text)
        print("[hotkey] Zwischenablage anonymisiert.", file=sys.stderr)

    def _do_deanonymize() -> None:
        try:
            text = clipboard.read()
        except ClipboardUnavailableError:
            return
        if not text:
            return
        clipboard.write(deanonymizer.deanonymize(text).text)
        print("[hotkey] Zwischenablage deanonymisiert.", file=sys.stderr)

    try:
        daemon = HotkeyDaemon(
            on_anonymize=_do_anonymize,
            on_deanonymize=_do_deanonymize,
            config=HotkeyConfig(
                anonymize=args.anonymize_hotkey,
                deanonymize=args.deanonymize_hotkey,
            ),
        )
    except HotkeyUnavailableError as exc:
        store.close()
        print(f"Fehler: {exc}", file=sys.stderr)
        return 17

    print(
        f"Hotkey-Daemon läuft (Profil '{args.profile}'). "
        f"Anonymize: {args.anonymize_hotkey}, Deanonymize: {args.deanonymize_hotkey}. "
        "Strg+C zum Beenden.",
        file=sys.stderr,
    )
    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        print("\nDaemon gestoppt.", file=sys.stderr)
    finally:
        store.close()
    return 0


def _cmd_model(args: argparse.Namespace, manager: ProfileManager) -> int:
    """ML-Modell-Verwaltung: Status anzeigen, herunterladen, entfernen.

    Exit-Codes:
    * 0 — Erfolg
    * 15 — Download benötigt Bestätigung (``--yes`` nicht gesetzt)
    * 16 — Download fehlgeschlagen (Netzwerk/HuggingFace nicht erreichbar)
    """
    from pseudokrat.pii.model_install import (
        ModelDownloadError,
        download_model,
        free_disk_bytes,
        model_status,
        remove_model,
    )

    settings = manager.settings
    sub = getattr(args, "subcommand", "status")

    if sub == "status":
        status = model_status(settings)
        if status.is_present:
            print(
                f"OK: Modell '{status.model_id}' liegt unter {status.cache_dir} "
                f"({status.gigabytes_on_disk:.2f} GB)."
            )
        else:
            print(
                f"NICHT VORHANDEN: Modell '{status.model_id}' im Cache {status.cache_dir} "
                "fehlt. Lade es mit:  pseudokrat model download --yes"
            )
        return 0

    if sub == "download":
        if not args.yes:
            free_gb = free_disk_bytes(settings.model_cache_dir) / (1024**3)
            print(
                f"Der Download lädt etwa 3 GB nach {settings.model_cache_dir}. "
                f"Verfügbarer Speicherplatz: {free_gb:.1f} GB.\n"
                "Bestätigen Sie mit:  pseudokrat model download --yes",
                file=sys.stderr,
            )
            return 15
        try:
            status = download_model(settings, progress=lambda m: print(m, file=sys.stderr))
        except ModelDownloadError as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 16
        print(f"Modell installiert: {status.cache_dir} ({status.gigabytes_on_disk:.2f} GB)")
        return 0

    if sub == "remove":
        bytes_freed = remove_model(settings)
        if bytes_freed == 0:
            print("Kein Modell-Cache vorhanden — nichts zu entfernen.")
        else:
            print(f"Modell-Cache entfernt. Freigegeben: {bytes_freed / (1024**3):.2f} GB.")
        return 0

    print(f"Fehler: Unbekanntes model-Subkommando '{sub}'", file=sys.stderr)
    return 1


def _cmd_audit(args: argparse.Namespace, manager: ProfileManager) -> int:
    try:
        store, audit = _open_profile(manager, args.profile, args.password)
    except InvalidPasswordError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    with store:
        if args.subcommand == "verify":
            ok = audit.verify_chain()
            print("OK" if ok else "MANIPULATION ERKANNT", file=sys.stdout)
            return 0 if ok else 4
        if args.subcommand == "export":
            export_format = getattr(args, "format", "csv")
            if export_format == "pdf":
                if args.output is None:
                    print("Fehler: --output ist für PDF-Export erforderlich.", file=sys.stderr)
                    return 6
                audit.export_pdf(args.output, profile_name=args.profile)
                print(f"[audit] PDF exportiert nach {args.output}", file=sys.stderr)
                return 0
            csv_data = audit.export_csv()
            if args.output is None:
                sys.stdout.write(csv_data)
            else:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(csv_data, encoding="utf-8")
            return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    manager = ProfileManager()

    if args.command == "init":
        return _cmd_init(args, manager)
    if args.command == "anonymize":
        return _cmd_anonymize(args, manager)
    if args.command == "deanonymize":
        return _cmd_deanonymize(args, manager)
    if args.command == "clipboard":
        return _cmd_clipboard(args, manager)
    if args.command == "profiles":
        return _cmd_profiles(args, manager)
    if args.command == "audit":
        return _cmd_audit(args, manager)
    if args.command == "model":
        return _cmd_model(args, manager)
    if args.command == "hotkey-daemon":
        return _cmd_hotkey_daemon(args, manager)
    if args.command == "server":
        return _cmd_server(args, manager)
    parser.error(f"Unbekannter Befehl: {args.command}")
    return 1  # type: ignore[unreachable]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
