"""Smoke-Tests für die CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.cli import main


def test_cli_anonymize_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", "pw")
    rc = main(
        [
            "anonymize",
            "--profile",
            "default",
            "--text",
            "Hofer Bau GmbH ist Mandant.",
            "--no-ml",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "<COMPANY_001>" in out


def test_cli_roundtrip_via_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", "pw")

    input_file = tmp_path / "in.txt"
    anon_file = tmp_path / "anon.txt"
    output_file = tmp_path / "out.txt"

    input_file.write_text("Vertrag mit Hofer Bau GmbH (UID ATU12345675).", encoding="utf-8")

    rc1 = main(
        [
            "anonymize",
            "--profile",
            "test",
            "-i",
            str(input_file),
            "-o",
            str(anon_file),
            "--no-ml",
        ]
    )
    assert rc1 == 0
    anonymized = anon_file.read_text(encoding="utf-8")
    assert "<COMPANY_001>" in anonymized
    assert "<UID_001>" in anonymized

    rc2 = main(
        [
            "deanonymize",
            "--profile",
            "test",
            "-i",
            str(anon_file),
            "-o",
            str(output_file),
        ]
    )
    assert rc2 == 0
    restored = output_file.read_text(encoding="utf-8")
    assert "Hofer Bau GmbH" in restored
    assert "ATU12345675" in restored


def test_cli_audit_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", "pw")

    rc = main(["anonymize", "--profile", "auditprof", "-t", "Hofer Bau GmbH", "--no-ml"])
    assert rc == 0
    capsys.readouterr()

    rc = main(["audit", "--profile", "auditprof", "verify"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_cli_profiles_list_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    rc = main(["profiles", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "keine Profile" in out


def test_cli_init_creates_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    rc = main(["init", "--profile", "Mandant Hofer", "--password", "ein-sicheres-pw"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Mandant Hofer" in out
    assert "Nächste Schritte" in out

    rc2 = main(["profiles", "list"])
    assert rc2 == 0
    listing = capsys.readouterr().out
    assert "Mandant Hofer" in listing


def test_cli_init_rejects_existing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    rc = main(["init", "--profile", "dup", "--password", "ein-sicheres-pw"])
    assert rc == 0
    capsys.readouterr()
    rc2 = main(["init", "--profile", "dup", "--password", "ein-sicheres-pw"])
    assert rc2 == 9
    err = capsys.readouterr().err
    assert "existiert bereits" in err


def test_cli_init_rejects_weak_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    rc = main(["init", "--profile", "weakpw", "--password", "kurz"])
    assert rc == 10
    err = capsys.readouterr().err
    assert "mindestens" in err


def test_cli_init_rejects_invalid_profile_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    rc = main(["init", "--profile", "bad/name", "--password", "ein-sicheres-pw"])
    assert rc == 11
    err = capsys.readouterr().err
    assert "ungültige Zeichen" in err


def test_cli_init_uses_env_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_PASSWORD", "env-passwort-xyz")
    rc = main(["init", "--profile", "envprofile"])
    assert rc == 0
    capsys.readouterr()
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")
    rc2 = main(
        [
            "anonymize",
            "--profile",
            "envprofile",
            "--text",
            "Hofer Bau GmbH",
            "--no-ml",
        ]
    )
    assert rc2 == 0


def test_cli_init_interactive_password_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PSEUDOKRAT_PASSWORD", raising=False)
    answers = iter(["passwort-eins", "passwort-zwei"])
    monkeypatch.setattr("pseudokrat.cli.getpass.getpass", lambda _prompt: next(answers))
    rc = main(["init", "--profile", "mismatch"])
    assert rc == 10
    err = capsys.readouterr().err
    assert "stimmen nicht überein" in err


def test_cli_init_interactive_password_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PSEUDOKRAT_PASSWORD", raising=False)
    answers = iter(["sicheres-passwort", "sicheres-passwort"])
    monkeypatch.setattr("pseudokrat.cli.getpass.getpass", lambda _prompt: next(answers))
    rc = main(["init", "--profile", "interactive"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "angelegt" in out


def test_cli_wrong_password_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")

    rc1 = main(
        [
            "anonymize",
            "--profile",
            "secret",
            "--password",
            "right",
            "-t",
            "Hofer Bau GmbH",
            "--no-ml",
        ]
    )
    assert rc1 == 0
    capsys.readouterr()

    rc2 = main(
        [
            "anonymize",
            "--profile",
            "secret",
            "--password",
            "wrong",
            "-t",
            "Test",
            "--no-ml",
        ]
    )
    assert rc2 == 2
