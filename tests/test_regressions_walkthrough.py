"""Regressions, die der E2E-Walkthrough aufgedeckt hat.

W-01: ``pseudokrat anonymize -i memo.txt`` ohne ``-o`` muss neben dem Original
      schreiben — nicht stdout. (Konsistent mit DOCX/XLSX/CSV.)
W-02: Der ``CompanyLegalFormRecognizer`` darf führende Wörter wie „Vertrag mit"
      nicht in den Span aufnehmen — sonst verliert das Profil die Konsistenz
      zwischen „Hofer Bau GmbH" (kurz) und „Vertrag mit Hofer Bau GmbH" (lang).
W-03: ``ProfileManager.list_profiles()`` muss den Original-Profilnamen (mit
      Leerzeichen) zurückliefern, nicht den Dateinamen-Slug.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.cli import main as cli_main
from pseudokrat.recognizers.company import CompanyLegalFormRecognizer
from pseudokrat.store.profile import ProfileManager


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", "pw")
    return tmp_path


def test_w01_txt_input_without_output_creates_anon_neighbor(_env: Path) -> None:
    src = _env / "memo.txt"
    src.write_text("Hofer Bau GmbH ist Mandant.", encoding="utf-8")
    rc = cli_main(["anonymize", "--profile", "w01", "-i", str(src), "--no-ml"])
    assert rc == 0
    target = src.with_name("memo.anon.txt")
    assert target.exists(), "TXT-Default-Output muss neben dem Original entstehen"
    assert "<COMPANY_001>" in target.read_text(encoding="utf-8")
    # Original bleibt unverändert
    assert src.read_text(encoding="utf-8") == "Hofer Bau GmbH ist Mandant."


def test_w02_company_recognizer_does_not_swallow_prefix() -> None:
    rec = CompanyLegalFormRecognizer()
    spans = rec.analyze("Vertrag mit Hofer Bau GmbH über die Bedingungen.")
    assert len(spans) == 1
    assert spans[0].text == "Hofer Bau GmbH", spans[0].text


def test_w02_company_consistency_between_short_and_long_sentence(_env: Path) -> None:
    """Egal in welchem Satz Hofer auftaucht — derselbe Platzhalter."""
    rc1 = cli_main(["anonymize", "--profile", "w02", "--text", "Hofer Bau GmbH", "--no-ml"])
    assert rc1 == 0
    src = _env / "vertrag.txt"
    src.write_text("Vertrag mit Hofer Bau GmbH über IBAN.", encoding="utf-8")
    rc2 = cli_main(["anonymize", "--profile", "w02", "-i", str(src), "--no-ml"])
    assert rc2 == 0
    anonymized = src.with_name("vertrag.anon.txt").read_text(encoding="utf-8")
    assert "<COMPANY_001>" in anonymized
    assert "<COMPANY_002>" not in anonymized


def test_w03_profiles_list_keeps_spaces_in_name(_env: Path) -> None:
    """`profiles list` muss „Mandant Hofer" zeigen, nicht den Dateinamen-Slug."""
    rc = cli_main(
        [
            "anonymize",
            "--profile",
            "Mandant Hofer",
            "--text",
            "Hofer Bau GmbH",
            "--no-ml",
        ]
    )
    assert rc == 0

    profiles = ProfileManager().list_profiles()
    names = {p.name for p in profiles}
    assert "Mandant Hofer" in names
    assert "Mandant_Hofer" not in names
