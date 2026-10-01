"""Tests für per-Profil konfigurierbare MandantenNummer-Recognizer (§7 Megaprompt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.cli import main
from pseudokrat.recognizers import (
    InvalidMandantenPatternError,
    compile_mandanten_pattern,
    recognizers_for_store,
)
from pseudokrat.store.mapping_store import MappingStore
from pseudokrat.store.profile import (
    MANDANTEN_PATTERN_METADATA_KEY,
    ProfileManager,
    read_profile_metadata,
)

PW = "demo-password-2026"


def test_compile_mandanten_pattern_accepts_valid_regex() -> None:
    compiled = compile_mandanten_pattern(r"M-\d{5}")
    assert compiled.search("Mandant M-12345 vorbei") is not None


def test_compile_mandanten_pattern_rejects_broken_regex() -> None:
    with pytest.raises(InvalidMandantenPatternError):
        compile_mandanten_pattern(r"M-(\d{5}")  # nicht geschlossene Gruppe


def test_mapping_store_set_get_delete_metadata(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password=PW, profile_name="Mandant Hofer")
    try:
        assert store.get_metadata("foo") is None
        store.set_metadata("foo", "bar")
        assert store.get_metadata("foo") == "bar"
        store.set_metadata("foo", "baz")  # ON CONFLICT UPDATE
        assert store.get_metadata("foo") == "baz"
        store.delete_metadata("foo")
        assert store.get_metadata("foo") is None
    finally:
        store.close()


def test_read_profile_metadata_works_without_password(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password=PW, profile_name="Mandant Hofer")
    try:
        store.set_metadata(MANDANTEN_PATTERN_METADATA_KEY, r"M-\d{5}")
    finally:
        store.close()
    # Erneutes Öffnen ohne Passwort über Helper:
    assert read_profile_metadata(db, MANDANTEN_PATTERN_METADATA_KEY) == r"M-\d{5}"
    # Nicht vorhandener Key:
    assert read_profile_metadata(db, "does-not-exist") is None


def test_recognizers_for_store_without_pattern_matches_defaults(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password=PW, profile_name="Default")
    try:
        bundle = recognizers_for_store(store)
        names = [r.name for r in bundle]
        assert "mandanten_nr" not in names
    finally:
        store.close()


def test_recognizers_for_store_appends_when_pattern_set(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password=PW, profile_name="Default")
    try:
        store.set_metadata(MANDANTEN_PATTERN_METADATA_KEY, r"M-\d{5}")
        bundle = recognizers_for_store(store)
        assert bundle[-1].name == "mandanten_nr"
        spans = bundle[-1].analyze("Kunde M-12345 hat Frage")
        assert len(spans) == 1
        assert spans[0].text == "M-12345"
        assert spans[0].category == "MANDANT_NR"
    finally:
        store.close()


def test_recognizers_for_store_raises_on_broken_pattern(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    store = MappingStore(db, password=PW, profile_name="Default")
    try:
        store.set_metadata(MANDANTEN_PATTERN_METADATA_KEY, r"M-(\d{5}")
        with pytest.raises(InvalidMandantenPatternError):
            recognizers_for_store(store)
    finally:
        store.close()


def test_cli_init_with_mandanten_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)
    rc = main(
        [
            "init",
            "--profile",
            "Kanzlei A",
            "--mandanten-pattern",
            r"MND-\d{4}",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "MND-" in out  # bestätigt im Output

    # Pattern persistiert und greift beim Anonymisieren
    rc2 = main(
        [
            "anonymize",
            "--profile",
            "Kanzlei A",
            "--text",
            "Bitte zu Mandant MND-4711 Rückfrage stellen.",
            "--no-ml",
        ]
    )
    assert rc2 == 0
    anon_out = capsys.readouterr().out
    assert "<MANDANT_NR_001>" in anon_out
    assert "MND-4711" not in anon_out


def test_cli_init_rejects_broken_mandanten_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)
    rc = main(
        [
            "init",
            "--profile",
            "Kanzlei B",
            "--mandanten-pattern",
            r"M-(\d{5}",
        ]
    )
    assert rc == 12
    err = capsys.readouterr().err
    assert "Mandanten-Pattern" in err
    # Profil darf bei Validierungsfehler NICHT angelegt worden sein
    pm = ProfileManager()
    assert not pm.profile_path("Kanzlei B").exists()


def test_cli_set_mandanten_pattern_updates_existing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    assert main(["init", "--profile", "Kanzlei C"]) == 0
    capsys.readouterr()

    rc = main(
        [
            "profiles",
            "set-mandanten-pattern",
            "--profile",
            "Kanzlei C",
            "--pattern",
            r"K-\d{3}",
        ]
    )
    assert rc == 0
    capsys.readouterr()

    # Pattern wirkt sofort
    rc2 = main(
        [
            "anonymize",
            "--profile",
            "Kanzlei C",
            "--text",
            "Akte K-042 prüfen.",
            "--no-ml",
        ]
    )
    assert rc2 == 0
    out = capsys.readouterr().out
    assert "<MANDANT_NR_001>" in out
    assert "K-042" not in out

    # show-mandanten-pattern liest ohne Passwort
    monkeypatch.delenv("PSEUDOKRAT_PASSWORD")
    rc3 = main(["profiles", "show-mandanten-pattern", "--profile", "Kanzlei C"])
    assert rc3 == 0
    assert capsys.readouterr().out.strip() == r"K-\d{3}"


def test_cli_set_mandanten_pattern_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    assert main(["init", "--profile", "K-Clear", "--mandanten-pattern", r"X-\d+"]) == 0
    capsys.readouterr()

    assert main(["profiles", "set-mandanten-pattern", "--profile", "K-Clear", "--clear"]) == 0
    capsys.readouterr()

    # Show liefert "kein Pattern hinterlegt"
    rc = main(["profiles", "show-mandanten-pattern", "--profile", "K-Clear"])
    assert rc == 0
    assert "kein Mandanten-Pattern" in capsys.readouterr().out


def test_cli_set_mandanten_pattern_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    assert main(["init", "--profile", "Valid"]) == 0
    capsys.readouterr()

    rc = main(
        [
            "profiles",
            "set-mandanten-pattern",
            "--profile",
            "Valid",
            "--pattern",
            r"M-(\d{5}",
        ]
    )
    assert rc == 12
    assert "Mandanten-Pattern" in capsys.readouterr().err


def test_cli_set_mandanten_pattern_conflicting_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    assert main(["init", "--profile", "Conf"]) == 0
    capsys.readouterr()

    rc = main(
        [
            "profiles",
            "set-mandanten-pattern",
            "--profile",
            "Conf",
            "--pattern",
            r"X-\d+",
            "--clear",
        ]
    )
    assert rc == 14
    assert "gleichzeitig" in capsys.readouterr().err


def test_cli_set_mandanten_pattern_no_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    assert main(["init", "--profile", "Noargs"]) == 0
    capsys.readouterr()

    rc = main(["profiles", "set-mandanten-pattern", "--profile", "Noargs"])
    assert rc == 14
    assert "--pattern" in capsys.readouterr().err


def test_cli_set_mandanten_pattern_missing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    rc = main(
        [
            "profiles",
            "set-mandanten-pattern",
            "--profile",
            "Ghost",
            "--pattern",
            r"G-\d+",
        ]
    )
    assert rc == 13
    assert "existiert nicht" in capsys.readouterr().err


def test_cli_show_mandanten_pattern_missing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    rc = main(["profiles", "show-mandanten-pattern", "--profile", "Nothing"])
    assert rc == 13
    assert "existiert nicht" in capsys.readouterr().err


def test_round_trip_with_mandanten_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Anonymize -> Deanonymize muss MANDANT_NR-Platzhalter zurückführen."""
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", PW)

    assert main(["init", "--profile", "RT", "--mandanten-pattern", r"M-\d{5}"]) == 0
    capsys.readouterr()

    text = "Akte M-12345 für Herrn Müller bei Hofer Bau GmbH."
    assert main(["anonymize", "--profile", "RT", "--text", text, "--no-ml"]) == 0
    anon = capsys.readouterr().out.strip()
    assert "<MANDANT_NR_001>" in anon
    assert "M-12345" not in anon

    assert main(["deanonymize", "--profile", "RT", "--text", anon]) == 0
    restored = capsys.readouterr().out.strip()
    assert "M-12345" in restored
