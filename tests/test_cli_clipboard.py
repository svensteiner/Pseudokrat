"""End-to-End-Tests für den `pseudokrat clipboard`-Subbefehl.

Der Subbefehl ist Workflow A aus §3 des Megaprompts: liest Text aus der
Zwischenablage, anonymisiert oder deanonymisiert ihn, und schreibt das
Ergebnis zurück. In Tests ersetzen wir die System-Zwischenablage durch eine
in-Memory-Variante (`InMemoryClipboard`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat import cli as cli_module
from pseudokrat import clipboard as clipboard_module
from pseudokrat.cli import main
from pseudokrat.clipboard import Clipboard, ClipboardUnavailableError, InMemoryClipboard


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isoliert jeden Test in einem eigenen Datenverzeichnis ohne ML-Pfad."""
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", "pw")


def _patch_clipboard(monkeypatch: pytest.MonkeyPatch, cb: Clipboard) -> None:
    """Ersetzt die Default-Zwischenablage in CLI- und Modul-Sicht."""

    def factory() -> Clipboard:
        return cb

    monkeypatch.setattr(cli_module, "default_clipboard", factory)
    monkeypatch.setattr(clipboard_module, "default_clipboard", factory)


def test_clipboard_anonymize_round_trip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cb = InMemoryClipboard(initial="Vertrag mit Hofer Bau GmbH (UID ATU12345675).")
    _patch_clipboard(monkeypatch, cb)

    rc = main(["clipboard", "--profile", "mandant", "anonymize", "--no-ml"])
    assert rc == 0
    anonymized = cb.read()
    assert "<COMPANY_001>" in anonymized
    assert "<UID_001>" in anonymized
    assert "Hofer Bau GmbH" not in anonymized

    captured = capsys.readouterr()
    assert "clipboard:anonymize" in captured.err
    assert "mandant" in captured.err


def test_clipboard_deanonymize_round_trip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cb = InMemoryClipboard(initial="Hofer Bau GmbH und ATU12345675.")
    _patch_clipboard(monkeypatch, cb)

    rc = main(["clipboard", "--profile", "m2", "anonymize", "--no-ml"])
    assert rc == 0
    anonymized = cb.read()
    capsys.readouterr()

    # Simuliere: KI antwortet mit dem anonymisierten Text — bleibt also in
    # der Zwischenablage. Jetzt deanonymisieren.
    rc2 = main(["clipboard", "--profile", "m2", "deanonymize"])
    assert rc2 == 0
    restored = cb.read()
    assert "Hofer Bau GmbH" in restored
    assert "ATU12345675" in restored
    assert anonymized != restored

    err = capsys.readouterr().err
    assert "clipboard:deanonymize" in err


def test_clipboard_empty_returns_dedicated_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cb = InMemoryClipboard(initial="")
    _patch_clipboard(monkeypatch, cb)

    rc = main(["clipboard", "--profile", "p", "anonymize", "--no-ml"])
    assert rc == 8
    assert "leer" in capsys.readouterr().err


def test_clipboard_unavailable_returns_dedicated_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken() -> Clipboard:
        raise ClipboardUnavailableError("pyperclip nicht installiert")

    monkeypatch.setattr(cli_module, "default_clipboard", broken)

    rc = main(["clipboard", "--profile", "p", "anonymize", "--no-ml"])
    assert rc == 7
    assert "pyperclip" in capsys.readouterr().err


def test_clipboard_deanonymize_missing_placeholder_returns_exit_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Frisches Profil ohne Mapping, aber Text enthält Platzhalter-ähnliche Tokens
    # mit Profil-Suffix — Deanonymisierung findet sie nicht, soll Exit 3 liefern.
    cb = InMemoryClipboard(initial="<COMPANY_999> ist unbekannt.")
    _patch_clipboard(monkeypatch, cb)

    rc = main(["clipboard", "--profile", "leer", "deanonymize"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "unbekannt" in err


def test_clipboard_anonymize_preserves_non_pii(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Beträge und Freitext ohne PII bleiben unverändert (§5 Punkt 4)."""
    original = "Bitte überweise 1.200,50 € — vielen Dank!"
    cb = InMemoryClipboard(initial=original)
    _patch_clipboard(monkeypatch, cb)

    rc = main(["clipboard", "--profile", "p", "anonymize", "--no-ml"])
    assert rc == 0
    assert cb.read() == original
    capsys.readouterr()
