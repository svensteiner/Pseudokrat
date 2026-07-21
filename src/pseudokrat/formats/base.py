"""Gemeinsame Typen und Protokolle für Format-Handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol
from zipfile import BadZipFile, ZipFile


class UnsupportedFormatError(ValueError):
    """Wird geworfen, wenn keine Handler-Klasse für ein Dateiformat existiert."""


class UnsafeArchiveError(ValueError):
    """Office archive is malformed or exceeds conservative resource limits."""


MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_ENTRY_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 2_000


def validate_office_archive(path: Path) -> None:
    """Validate OOXML ZIP structure before a parser allocates its contents.

    Handlers do not extract entries to disk, but hostile central-directory
    sizes, compression bombs, encrypted members, duplicates, and traversal
    names can still produce denial of service or parser ambiguity.
    """
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
    except (BadZipFile, OSError) as exc:
        raise UnsafeArchiveError("Office-Datei ist kein gültiges ZIP-Archiv.") from exc
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise UnsafeArchiveError("Office-Archiv enthält zu viele Einträge.")
    seen: set[str] = set()
    total_size = 0
    for entry in entries:
        name = entry.filename
        member_path = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or "\x00" in name
            or member_path.is_absolute()
            or ".." in member_path.parts
        ):
            raise UnsafeArchiveError("Office-Archiv enthält einen unsicheren Pfad.")
        if name in seen:
            raise UnsafeArchiveError("Office-Archiv enthält doppelte Einträge.")
        seen.add(name)
        if entry.flag_bits & 0x1:
            raise UnsafeArchiveError("Verschlüsselte Office-Archive werden nicht verarbeitet.")
        if entry.file_size > MAX_ARCHIVE_ENTRY_BYTES:
            raise UnsafeArchiveError("Office-Archiv enthält einen zu großen Eintrag.")
        total_size += entry.file_size
        if total_size > MAX_ARCHIVE_TOTAL_BYTES:
            raise UnsafeArchiveError("Office-Archiv ist entpackt zu groß.")
        if entry.file_size > 1024 * 1024:
            ratio = entry.file_size / max(1, entry.compress_size)
            if ratio > MAX_ARCHIVE_COMPRESSION_RATIO:
                raise UnsafeArchiveError("Office-Archiv hat eine unplausible Kompressionsrate.")


# Eine Transform-Funktion erhält einen Text-String (z. B. einen Absatz, eine
# Zelle, einen ganzen TXT-Inhalt) und liefert die anonymisierte Variante.
TextTransform = Callable[[str], str]


@dataclass(frozen=True)
class FormatProcessResult:
    """Resultat einer Datei-Anonymisierung."""

    input_path: Path
    output_path: Path
    segments_processed: int = 0
    segments_skipped: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


class FormatHandler(Protocol):
    """Format-spezifische Read/Write/Transform-Strategie."""

    name: str

    def supports(self, path: Path) -> bool: ...

    def process(
        self,
        input_path: Path,
        output_path: Path,
        transform: TextTransform,
    ) -> FormatProcessResult: ...

    def default_output_path(self, input_path: Path, suffix: str = "anon") -> Path: ...


def derive_default_output(input_path: Path, suffix: str = "anon") -> Path:
    """``foo.csv`` → ``foo.anon.csv``."""
    stem = input_path.stem
    return input_path.with_name(f"{stem}.{suffix}{input_path.suffix}")
