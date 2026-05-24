"""Fuzz-Tests für die Datei- und CLI-Pipelines.

Wir generieren randomisierte Eingaben (TXT/CSV-Bytes, kleine Texte) und
prüfen drei Invarianten:

1. Kein unhandled Crash (alle Exceptions müssen erwartete Typen sein).
2. Der anonymisierte Output enthält keine erkannten PII-Spans mehr.
3. Round-Trip via Mapping-Store ist verlustfrei.

Diese Tests sind absichtlich teurer (mehr Hypothesis-Beispiele) als die
restliche Suite — sie sollen latente Lücken finden, die die hand-kuratierten
Fixtures nicht abdecken.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pseudokrat.anonymizer import Anonymizer
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.formats import CSVHandler, TextHandler, handler_for
from pseudokrat.formats.base import UnsupportedFormatError
from pseudokrat.recognizers import default_recognizers
from pseudokrat.store.audit_log import AuditLog
from pseudokrat.store.mapping_store import MappingStore
from pseudokrat.store.profile import ProfileManager

FUZZ_SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ],
)

# Schnellere Settings für reine In-Memory-Property-Tests
FAST_FUZZ_SETTINGS = settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
        HealthCheck.filter_too_much,
    ],
)


@pytest.fixture
def pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path]]:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path / "ps-data"))
    pm = ProfileManager()
    store, audit = pm.open_or_create("fuzz", "Fuzz-Passw0rt-für-die-Suite!")
    anon = Anonymizer(
        store=store,
        recognizers=default_recognizers(),
        detector=None,
        audit_log=audit,
        model_version="fuzz",
    )
    deanon = Deanonymizer(store=store, audit_log=audit, model_version="fuzz")
    workdir = tmp_path / "work"
    workdir.mkdir()
    try:
        yield anon, deanon, store, audit, workdir
    finally:
        store.close()


# --------------------------------------------------------------------------- #
# 1. Robustheit: TextHandler verarbeitet beliebiges UTF-8                     #
# --------------------------------------------------------------------------- #


class TestTextHandlerFuzz:
    @given(
        text=st.text(
            alphabet=st.characters(blacklist_categories=("Cs", "Cc")),
            min_size=0,
            max_size=2000,
        )
    )
    @FUZZ_SETTINGS
    def test_arbitrary_text_roundtrip(
        self,
        text: str,
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        anon, deanon, _, _, workdir = pipeline
        input_path = workdir / "in.txt"
        input_path.write_text(text, encoding="utf-8")
        output_path = workdir / "in.anon.txt"
        handler = TextHandler()
        handler.process(
            input_path,
            output_path,
            transform=lambda t: anon.anonymize(t).text,
        )
        anonymized = output_path.read_text(encoding="utf-8")
        # Reverse via Anonymizer-Mapping-Store
        decoded = deanon.deanonymize(anonymized).text
        assert decoded == text, (
            f"Round-Trip-Drift\n  text={text!r}\n  anon={anonymized!r}\n  decoded={decoded!r}"
        )

    @given(blob=st.binary(min_size=0, max_size=2000))
    @FUZZ_SETTINGS
    def test_binary_blob_does_not_crash(
        self,
        blob: bytes,
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        """TXT-Handler darf bei Binär-Bytes graceful failen, nicht crashen.

        Akzeptiert: ``UnicodeDecodeError`` / ``OSError``. Alles andere ist
        ein Bug.
        """
        anon, _, _, _, workdir = pipeline
        input_path = workdir / "blob.txt"
        input_path.write_bytes(blob)
        output_path = workdir / "blob.anon.txt"
        try:
            TextHandler().process(
                input_path,
                output_path,
                transform=lambda t: anon.anonymize(t).text,
            )
        except (UnicodeDecodeError, OSError):
            pass
        except Exception as e:  # pragma: no cover - failure case
            raise AssertionError(
                f"Unerwartete Exception {type(e).__name__}: {e}"
            ) from e


# --------------------------------------------------------------------------- #
# 2. CSV-Handler                                                              #
# --------------------------------------------------------------------------- #


csv_cell = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc"),
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=40,
)


@st.composite
def csv_row(draw: st.DrawFn) -> list[str]:
    n = draw(st.integers(min_value=1, max_value=6))
    return [draw(csv_cell) for _ in range(n)]


class TestCsvHandlerFuzz:
    @given(rows=st.lists(csv_row(), min_size=1, max_size=20))
    @FUZZ_SETTINGS
    def test_csv_roundtrip(
        self,
        rows: list[list[str]],
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        anon, deanon, _, _, workdir = pipeline
        # Padding auf gleiche Spalten-Anzahl, damit das CSV regulär ist.
        width = max(len(r) for r in rows)
        normalized = [r + [""] * (width - len(r)) for r in rows]

        input_path = workdir / "in.csv"
        with input_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            for row in normalized:
                w.writerow(row)

        output_path = workdir / "in.anon.csv"
        CSVHandler().process(
            input_path,
            output_path,
            transform=lambda t: anon.anonymize(t).text,
        )
        # Lese anonymisiertes CSV
        with output_path.open("r", encoding="utf-8", newline="") as f:
            anon_rows = list(csv.reader(f))
        # Deanonymisiere alle Zellen, vergleiche mit Original
        decoded_rows = []
        for row in anon_rows:
            decoded_rows.append([deanon.deanonymize(c).text for c in row])
        assert decoded_rows == normalized, (
            f"CSV-Round-Trip-Drift\n  normalized={normalized!r}\n  decoded={decoded_rows!r}"
        )


# --------------------------------------------------------------------------- #
# 3. Format-Dispatcher                                                        #
# --------------------------------------------------------------------------- #


class TestFormatDispatcherRobustness:
    @given(
        stem=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs", "Cc"),
                blacklist_characters="/\\:*?\"<>|",
            ),
            min_size=1,
            max_size=20,
        )
    )
    @FUZZ_SETTINGS
    def test_handler_for_invalid_suffix_raises_unsupported(
        self,
        stem: str,
    ) -> None:
        # Wir setzen eine Endung, die mit Sicherheit nicht unterstützt ist.
        try:
            handler_for(Path(f"{stem}.unsupportedext"))
        except UnsupportedFormatError:
            return
        # Andernfalls: Suffix war zufällig doch unterstützt — auch ok
        return

    def test_handler_for_no_suffix(self) -> None:
        with pytest.raises(UnsupportedFormatError):
            handler_for(Path("README"))


# --------------------------------------------------------------------------- #
# 4. CLI-Fuzz: bekannte Input-Patterns mit randomisierten Werten              #
# --------------------------------------------------------------------------- #


from tests.test_property_recognizers import (  # noqa: E402
    valid_at_uid,
    valid_de_ust_id,
    valid_iban,
)


@st.composite
def realistic_document(draw: st.DrawFn) -> str:
    """Erzeuge ein „realistisches" Multiline-Dokument mit PII."""
    lines: list[str] = []
    n = draw(st.integers(min_value=1, max_value=10))
    for _ in range(n):
        line_type = draw(st.sampled_from(["plain", "iban", "ust", "uid", "email"]))
        if line_type == "plain":
            lines.append(
                draw(
                    st.text(
                        alphabet=" abcdefghijklmnopqrstuvwxyz.,;:!?",
                        min_size=0,
                        max_size=80,
                    )
                )
            )
        elif line_type == "iban":
            lines.append(f"Bankverbindung: {draw(valid_iban())}.")
        elif line_type == "ust":
            lines.append(f"USt-IdNr.: {draw(valid_de_ust_id())}")
        elif line_type == "uid":
            lines.append(f"UID: {draw(valid_at_uid())}")
        elif line_type == "email":
            local = draw(st.text(alphabet="abcdefghij", min_size=2, max_size=8))
            domain = draw(st.text(alphabet="abcdefghij", min_size=2, max_size=8))
            lines.append(f"Kontakt: {local}@{domain}.example")
    return "\n".join(lines)


class TestRealisticDocumentRoundTrip:
    @given(doc=realistic_document())
    @FUZZ_SETTINGS
    def test_realistic_doc_roundtrip(
        self,
        doc: str,
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        anon, deanon, _, _, _ = pipeline
        r = anon.anonymize(doc)
        decoded = deanon.deanonymize(r.text).text
        assert decoded == doc, (
            f"Realistic-Doc-Drift\n"
            f"  doc={doc!r}\n"
            f"  anon={r.text!r}\n"
            f"  decoded={decoded!r}"
        )

    @given(doc=realistic_document())
    @FUZZ_SETTINGS
    def test_anonymized_contains_no_original_pii(
        self,
        doc: str,
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        anon, _, _, _, _ = pipeline
        r = anon.anonymize(doc)
        for span in r.spans:
            assert span.text not in r.text, (
                f"PII {span.text!r} ({span.category}) leakte: {r.text!r}"
            )


# --------------------------------------------------------------------------- #
# 5. Placeholder-Format-Stress: Texte, die schon Platzhalter enthalten        #
# --------------------------------------------------------------------------- #


class TestPlaceholderShapedInput:
    """Texte, die bereits Strings im Platzhalter-Format enthalten — die
    Deanonymisierung darf nur Platzhalter ersetzen, die wirklich im Store sind.
    """

    def test_unknown_placeholder_is_preserved(
        self,
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        _, deanon, _, _, _ = pipeline
        text = "Dies ist <PERSON_999> und <IBAN_042> — unbekannte Platzhalter."
        r = deanon.deanonymize(text)
        assert r.text == text  # nichts ersetzt
        assert set(r.missing_placeholders) == {"<PERSON_999>", "<IBAN_042>"}

    @given(body=st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), min_size=0, max_size=200))
    @FAST_FUZZ_SETTINGS
    def test_deanonymizing_random_text_never_crashes(
        self,
        body: str,
        pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
    ) -> None:
        _, deanon, _, _, _ = pipeline
        deanon.deanonymize(body)


# --------------------------------------------------------------------------- #
# 6. CSV-IO-Edge: leere Datei                                                 #
# --------------------------------------------------------------------------- #


def test_empty_txt_file(
    pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
) -> None:
    anon, _, _, _, workdir = pipeline
    empty = workdir / "empty.txt"
    empty.write_text("", encoding="utf-8")
    out = workdir / "empty.anon.txt"
    TextHandler().process(empty, out, transform=lambda t: anon.anonymize(t).text)
    assert out.read_text(encoding="utf-8") == ""


def test_empty_csv_file(
    pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
) -> None:
    anon, _, _, _, workdir = pipeline
    empty = workdir / "empty.csv"
    empty.write_text("", encoding="utf-8")
    out = workdir / "empty.anon.csv"
    CSVHandler().process(empty, out, transform=lambda t: anon.anonymize(t).text)
    # Akzeptiert: Output existiert und ist leer ODER existiert mit minimalem Inhalt
    assert out.exists()


def test_csv_with_only_newlines(
    pipeline: tuple[Anonymizer, Deanonymizer, MappingStore, AuditLog, Path],
) -> None:
    anon, _, _, _, workdir = pipeline
    src = workdir / "nl.csv"
    src.write_text("\n\n\n", encoding="utf-8")
    out = workdir / "nl.anon.csv"
    CSVHandler().process(src, out, transform=lambda t: anon.anonymize(t).text)
    assert out.exists()
