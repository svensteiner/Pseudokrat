"""CLI surface for the local KI-development workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pseudokrat.ki_project import (
    ProjectError,
    prepare_original_workspace,
    prepare_project,
    publish_project,
    restore_file,
)


def add_commands(sub: Any, common: argparse.ArgumentParser) -> None:
    parser = sub.add_parser("ki-project", parents=[common], help="Excel/Word für KI-Codeentwicklung vorbereiten.")
    actions = parser.add_subparsers(dest="ki_action", required=True)
    prepare = actions.add_parser("prepare", help="Lokale Vorschau und verschlüsselte Zuordnung erstellen.")
    prepare.add_argument("--input", nargs="+", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--terms", type=Path, help="Lokale UTF-8-Datei: ein zusätzlich zu ersetzender Begriff je Zeile.")
    prepare.add_argument("--local-endpoint", help="Optional: OpenAI-kompatibler lokaler Endpunkt, z. B. http://127.0.0.1:1234/v1")
    prepare.add_argument("--local-model", help="Exakte Modellkennung des eigenen Servers.")
    prepare.add_argument("--allow-lan", action="store_true", help="Originaltext ausdrücklich an die gewählte private Spark-IP senden.")
    release = actions.add_parser("publish", help="Geprüfte Vorschau als KI-Paket exportieren.")
    release.add_argument("--project", required=True, type=Path)
    release.add_argument("--reviewed", action="store_true")
    release.add_argument("--accept-numeric-linkability", action="store_true")
    restore = actions.add_parser("restore", help="Projekt-Platzhalter lokal zurückwandeln.")
    restore.add_argument("--project", required=True, type=Path)
    restore.add_argument("--input", required=True, type=Path)
    restore.add_argument("--output", required=True, type=Path)
    local = actions.add_parser("local-workspace", help="VERTRAULICHE Originaldaten für den eigenen Spark vorbereiten.")
    local.add_argument("--project", required=True, type=Path)
    local.add_argument("--output", required=True, type=Path)


def run(args: argparse.Namespace, manager: Any) -> int:
    from pseudokrat.cli import _open_profile

    store = None
    try:
        store, _ = _open_profile(manager, args.profile, args.password)
        key = store.keys.fernet
        if args.ki_action == "prepare":
            terms = []
            if args.terms:
                terms = [t.strip() for t in args.terms.read_text(encoding="utf-8-sig").splitlines()
                         if t.strip() and not t.lstrip().startswith("#")]
            detector = None
            if args.local_endpoint:
                from pseudokrat.pii.local_project_detector import LocalProjectDetector

                detector = LocalProjectDetector(args.local_endpoint, args.local_model or "", allow_lan=args.allow_lan)
            elif args.local_model or args.allow_lan:
                raise ProjectError("Lokalen Endpunkt zusammen mit Modellkennung angeben.")
            prepare_project(args.input, args.output, key, terms=terms, detector=detector)
            print("Lokale Vorschau erstellt. Vollständig prüfen; Originale und Zuordnung bleiben lokal.")
        elif args.ki_action == "publish":
            publish_project(args.project, key, reviewed=args.reviewed,
                            accept_numeric_linkability=args.accept_numeric_linkability)
            print("KI-Paket.zip erstellt. Nur dieses Paket weitergeben, niemals den Projektordner.")
        elif args.ki_action == "restore":
            restore_file(args.project, key, args.input, args.output)
            print("Datei lokal zurückgewandelt.")
        elif args.ki_action == "local-workspace":
            prepare_original_workspace(args.project, key, args.output)
            print("VERTRAULICHER Arbeitsordner erstellt. Enthält Originaldaten; nur auf dem eigenen Spark verwenden.")
        return 0
    except ProjectError as exc:
        print(f"KI-Projekt: {exc}", file=sys.stderr)
        return 20
    except (OSError, ValueError):
        print("KI-Projekt konnte nicht verarbeitet werden. Profil und lokale Dateien prüfen.", file=sys.stderr)
        return 20
    finally:
        if store is not None:
            store.close()
