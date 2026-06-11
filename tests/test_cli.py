"""Smoke-Tests für die CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.cli import main


def test_ensure_utf8_console_repariert_cp1252_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auf cp1252-Konsolen (deutsches Windows) darf kein print() der CLI
    an Umlauten oder Pfeilen (→) sterben — die gefrorene EXE crashte
    sonst direkt im Setup-Menü."""
    import io
    import sys

    from pseudokrat.cli import _ensure_utf8_console

    raw = io.BytesIO()
    cp1252_stdout = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", cp1252_stdout)

    # Vorbedingung: ohne Fix wirft cp1252 bei '→' einen UnicodeEncodeError.
    with pytest.raises(UnicodeEncodeError):
        cp1252_stdout.write("→")

    _ensure_utf8_console()

    print("Pseudokrat — Einrichtung → läuft")  # darf nicht mehr werfen
    sys.stdout.flush()
    assert b"Einrichtung" in raw.getvalue()


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


# ---------------------------------------------------------------------------
# profiles remove (Iter-14)
# ---------------------------------------------------------------------------


class TestProfilesRemove:
    """``pseudokrat profiles remove`` — Self-Service-Löschung mit Confirm.

    Pilot-Tester braucht ein klares Kommando, sobald Doctor ein Profil
    als kaputt meldet. Vorher zeigte der Doctor-Hint auf ein
    nicht-existierendes Kommando — das war Inkonsistenz pur."""

    @staticmethod
    def _make_simple_profile(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "Wegwerf"
    ) -> Path:
        monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
        # Init im Simple-Mode geht über init --simple ohne Passwort.
        # Wir umgehen das hier mit direktem ProfileManager-Setup für
        # determined Backend-Injection.
        from pseudokrat.config import Settings
        from pseudokrat.store.key_protector import InMemoryKeyringBackend
        from pseudokrat.store.profile import ProfileManager

        settings = Settings(
            data_dir=tmp_path,
            profiles_dir=tmp_path / "profiles",
            model_cache_dir=tmp_path / "models",
            model_id="dummy/model",
            disable_ml=True,
        )
        settings.ensure_dirs()
        mgr = ProfileManager(settings=settings)
        store, _ = mgr.open_or_create_simple(name, backend=InMemoryKeyringBackend())
        store.close()
        return mgr.profile_path(name)

    def test_remove_nonexistent_profile_fails_cleanly(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
        rc = main(["profiles", "remove", "ExistiertNicht", "--force"])
        assert rc == 13
        err = capsys.readouterr().err
        assert "existiert nicht" in err

    def test_remove_with_force_deletes_all_artifacts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        db_path = self._make_simple_profile(tmp_path, monkeypatch, "ZuLöschen")
        salt = db_path.with_suffix(db_path.suffix + ".salt")
        marker = db_path.with_suffix(db_path.suffix + ".keyring")
        assert db_path.exists() and salt.exists() and marker.exists()

        rc = main(["profiles", "remove", "ZuLöschen", "--force"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Gelöscht" in out
        assert not db_path.exists()
        assert not salt.exists()
        assert not marker.exists()

    def test_remove_without_force_prompts_and_can_abort(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        db_path = self._make_simple_profile(tmp_path, monkeypatch, "Bleibt")
        monkeypatch.setattr("builtins.input", lambda _prompt="": "nein")
        rc = main(["profiles", "remove", "Bleibt"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Abgebrochen" in out
        # Datei darf nicht gelöscht worden sein.
        assert db_path.exists()

    def test_remove_without_force_prompts_and_can_confirm(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        db_path = self._make_simple_profile(tmp_path, monkeypatch, "Bestätigt")
        monkeypatch.setattr("builtins.input", lambda _prompt="": "ja")
        rc = main(["profiles", "remove", "Bestätigt"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Gelöscht" in out
        assert not db_path.exists()

    def test_remove_invalid_name_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
        rc = main(["profiles", "remove", "../evil", "--force"])
        assert rc == 11
        err = capsys.readouterr().err
        assert "ungültige Zeichen" in err

    def test_remove_password_profile_does_not_touch_os_keyring(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Passwort-Profile haben keinen Keyring-Marker — wir dürfen den
        OS-Keyring-Eintrag dann NICHT anfassen (potentiell anderes
        Pseudokrat-Profil mit demselben Account-Namen)."""
        monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
        rc = main(["init", "--profile", "pwprof", "--password", "ein-sicheres-pw"])
        assert rc == 0
        capsys.readouterr()
        from pseudokrat.config import Settings
        from pseudokrat.store.profile import ProfileManager

        settings = Settings.load()
        mgr = ProfileManager(settings=settings)
        db_path = mgr.profile_path("pwprof")
        marker = db_path.with_suffix(db_path.suffix + ".keyring")
        assert not marker.exists()

        # Inject ein Sentinel-Keyring-Backend; assert dass es NICHT gerufen wird.
        deleted_accounts: list[str] = []

        class _SpyBackend:
            def get(self, service: str, account: str) -> str | None:
                return None

            def set(self, service: str, account: str, secret: str) -> None:
                pass

            def delete(self, service: str, account: str) -> None:
                deleted_accounts.append(account)

        monkeypatch.setattr(
            "pseudokrat.cli.SystemKeyringBackend",
            _SpyBackend,
            raising=False,
        )
        rc = main(["profiles", "remove", "pwprof", "--force"])
        assert rc == 0
        assert not db_path.exists()
        assert deleted_accounts == []
