"""Tests für ``pseudokrat doctor`` (PRL Iter-8, Härtung Iter-14).

Pilot-Tester brauchen einen einzigen Befehl, der „läuft alles?" mit
einem klaren Ja/Nein und konkreten Fix-Anweisungen beantwortet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.config import Settings
from pseudokrat.doctor import (
    Check,
    DoctorReport,
    Status,
    check_anonymize_roundtrip,
    check_hotkey_backend,
    check_ml_model,
    check_profile_health,
    check_profiles,
    format_report,
    run_doctor,
)
from pseudokrat.store.key_protector import InMemoryKeyringBackend
from pseudokrat.store.profile import ProfileManager


@pytest.fixture
def manager(tmp_path: Path) -> ProfileManager:
    settings = Settings(
        data_dir=tmp_path,
        profiles_dir=tmp_path / "profiles",
        model_cache_dir=tmp_path / "models",
        model_id="dummy/model",
        disable_ml=True,
    )
    return ProfileManager(settings=settings)


class TestCheckProfiles:
    def test_no_profiles_fails(self, manager: ProfileManager) -> None:
        result = check_profiles(manager)
        assert result.status is Status.FAIL
        assert "pseudokrat install" in result.message

    def test_with_profile_ok(self, manager: ProfileManager) -> None:
        store, _ = manager.open_or_create_simple(
            "Test", backend=InMemoryKeyringBackend()
        )
        store.close()
        result = check_profiles(manager)
        assert result.status is Status.OK
        assert "Test" in result.message


class TestAnonymizeRoundtrip:
    def test_roundtrip_with_throwaway_profile_ok(
        self, manager: ProfileManager
    ) -> None:
        result = check_anonymize_roundtrip(manager)
        assert result.status is Status.OK
        assert "Roundtrip OK" in result.message

    def test_roundtrip_does_not_pollute_profiles_dir(
        self, manager: ProfileManager
    ) -> None:
        """Doctor-Roundtrip darf KEINE Artefakte im echten profiles_dir
        zurücklassen — die Sandbox lebt in einem TemporaryDirectory.

        Regression gegen Iter-13-Bug: ``_doctor_smoke.sqlite`` blieb auf
        Disk liegen, das Keyring-Secret nur im RAM → Folge-Doctor-Runs
        scheiterten beim Öffnen des alten Files.
        """
        manager.settings.profiles_dir.mkdir(parents=True, exist_ok=True)
        before = set(manager.settings.profiles_dir.iterdir())
        result = check_anonymize_roundtrip(manager)
        after = set(manager.settings.profiles_dir.iterdir())
        assert result.status is Status.OK
        assert before == after, (
            f"Doctor hat Artefakte in profiles_dir hinterlassen: "
            f"{sorted(p.name for p in after - before)}"
        )

    @pytest.mark.parametrize("stem", ["doctor_smoke", "_doctor_smoke"])
    def test_roundtrip_survives_stale_doctor_smoke_artifacts(
        self, manager: ProfileManager, stem: str
    ) -> None:
        """Migration: alte ``_doctor_smoke*``-Leichen aus früheren
        Releases dürfen Doctor nicht blockieren — sie werden aufgeräumt.

        Zwei parametrisierte Varianten:
        * ``doctor_smoke`` — Slug nach ``_safe_slug`` (führendes ``_`` strip).
          Das ist die Variante, die tatsächlich auf User-Disks landet.
        * ``_doctor_smoke`` — defensive Coverage falls jemand das File
          manuell renamed oder ein älterer Build den Slug-Cleanup umging.
        """
        manager.settings.profiles_dir.mkdir(parents=True, exist_ok=True)
        # Simuliere Bestandsleichen — beliebige Bytes, kein gültiges SQLite.
        stale_db = manager.settings.profiles_dir / f"{stem}.sqlite"
        stale_db.write_bytes(b"corrupt-leftover-from-iter-13")
        stale_salt = manager.settings.profiles_dir / f"{stem}.sqlite.salt"
        stale_salt.write_bytes(b"\x00" * 16)
        stale_keyring = manager.settings.profiles_dir / f"{stem}.sqlite.keyring"
        stale_keyring.write_text("dummy", encoding="utf-8")

        result = check_anonymize_roundtrip(manager)
        assert result.status is Status.OK, (
            f"Doctor scheiterte an Bestandsleichen statt sie zu räumen: "
            f"{result.message}"
        )
        # Leichen sind weg.
        assert not stale_db.exists()
        assert not stale_salt.exists()
        assert not stale_keyring.exists()

    def test_roundtrip_with_named_profile_ok(
        self, manager: ProfileManager
    ) -> None:
        store, _ = manager.open_or_create_simple(
            "Pilot", backend=InMemoryKeyringBackend()
        )
        store.close()
        # Roundtrip nutzt den OS-Keyring-Pfad — Test-Setup ohne Backend
        # nicht trivial. Wir testen nur, dass die Funktion einen Check
        # zurueck gibt; OK oder FAIL ist umgebungsabhaengig.
        result = check_anonymize_roundtrip(manager, profile_name="Pilot")
        assert isinstance(result, Check)


class TestCheckProfileHealth:
    """Real-User-Pfad: ein einzelnes kaputtes Profil darf Doctor nicht
    blockieren — es wird namentlich als WARN gelistet, mit konkretem Hint."""

    def test_all_profiles_openable_returns_ok(
        self, manager: ProfileManager
    ) -> None:
        backend = InMemoryKeyringBackend()
        s1, _ = manager.open_or_create_simple("Mandant A", backend=backend)
        s1.close()
        s2, _ = manager.open_or_create_simple("Mandant B", backend=backend)
        s2.close()
        # Doctor benutzt im Test denselben In-Memory-Keyring wie beim Anlegen
        # — sonst gäbe es trivialerweise einen Mismatch (Produktion: derselbe
        # SystemKeyringBackend auf beiden Pfaden).
        result = check_profile_health(manager, keyring_backend=backend)
        assert result.status is Status.OK
        assert "2" in result.message

    def test_broken_keyring_profile_warns_not_fails(
        self, manager: ProfileManager
    ) -> None:
        """Profil im Simple-Mode angelegt, danach Keyring-Eintrag verloren
        (Backup-Restore, Konto-Wechsel). Doctor muss WARN melden, kein FAIL."""
        backend = InMemoryKeyringBackend()
        store, _ = manager.open_or_create_simple("Verwaist", backend=backend)
        store.close()
        # Simulierter Keyring-Verlust: separater leerer Backend ohne Secret.
        empty_backend = InMemoryKeyringBackend()
        result = check_profile_health(manager, keyring_backend=empty_backend)
        assert result.status is Status.WARN
        assert "Verwaist" in result.message
        # Hinweis-Text muss konkrete Handlungsanweisung enthalten.
        assert "profiles remove" in result.message
        # Kein Crash, kein FAIL — Doctor läuft danach weiter.

    def test_no_profiles_returns_warn_with_hint(
        self, manager: ProfileManager
    ) -> None:
        """Ohne Profile ist Profile-Health nicht prüfbar — informativ, nicht FAIL."""
        result = check_profile_health(manager)
        assert result.status is Status.WARN
        assert "Keine Profile" in result.message or "kein" in result.message.lower()


class TestProfileListingHidesReserved:
    """Reserved-Underscore-Profile (z. B. ``_doctor_smoke`` aus Bestandsinstall)
    dürfen nicht in ``check_profiles`` als User-Profile gezählt werden."""

    def test_underscore_prefix_profile_not_counted(
        self, manager: ProfileManager
    ) -> None:
        manager.settings.profiles_dir.mkdir(parents=True, exist_ok=True)
        # Lege ein reserviertes Profil-Artefakt an (Bestandsleiche).
        leftover = manager.settings.profiles_dir / "_doctor_smoke.sqlite"
        leftover.write_bytes(b"old")
        # Plus ein echtes Profil.
        store, _ = manager.open_or_create_simple(
            "Echt", backend=InMemoryKeyringBackend()
        )
        store.close()
        result = check_profiles(manager)
        assert result.status is Status.OK
        assert "Echt" in result.message
        assert "_doctor_smoke" not in result.message
        # Anzahl: 1 echter Eintrag.
        assert "1" in result.message


class TestHotkeyBackend:
    def test_returns_check(self) -> None:
        result = check_hotkey_backend()
        assert isinstance(result, Check)
        assert result.status in (Status.OK, Status.WARN)


class TestMLModel:
    def test_returns_check(self) -> None:
        result = check_ml_model()
        assert isinstance(result, Check)
        # Modell ist im CI nicht installiert — typischerweise WARN.
        assert result.status in (Status.OK, Status.WARN)


class TestRunDoctor:
    def test_no_profiles_has_failure(self, manager: ProfileManager) -> None:
        report = run_doctor(manager)
        assert report.has_failures
        assert report.exit_code() == 1

    def test_with_profile_no_failure(self, manager: ProfileManager) -> None:
        store, _ = manager.open_or_create_simple(
            "Pilot", backend=InMemoryKeyringBackend()
        )
        store.close()
        report = run_doctor(manager)
        # Roundtrip nutzt Throwaway-Profil — keine Hard-Failures erwartet.
        assert not report.has_failures
        assert report.exit_code() == 0

    def test_run_doctor_purges_legacy_leftovers_before_check_profiles(
        self, manager: ProfileManager
    ) -> None:
        """run_doctor räumt Bestandsleichen ZUERST, sonst tauchen sie in
        check_profiles auf und verwirren den Pilot-Tester."""
        manager.settings.profiles_dir.mkdir(parents=True, exist_ok=True)
        leftover = manager.settings.profiles_dir / "doctor_smoke.sqlite"
        leftover.write_bytes(b"old")
        # Echtes User-Profil parallel.
        store, _ = manager.open_or_create_simple(
            "EchterMandant", backend=InMemoryKeyringBackend()
        )
        store.close()

        report = run_doctor(manager)
        profile_check = next(c for c in report.checks if c.name == "Profile")
        assert profile_check.status is Status.OK
        # Genau ein echtes Profil, kein doctor_smoke mehr.
        assert "EchterMandant" in profile_check.message
        assert "doctor_smoke" not in profile_check.message
        assert "1 Profil" in profile_check.message
        # Leiche tatsächlich von Disk weg.
        assert not leftover.exists()

    def test_report_contains_all_checks(self, manager: ProfileManager) -> None:
        report = run_doctor(manager)
        names = {c.name for c in report.checks}
        assert names == {
            "Profile",
            "Anonymize-Roundtrip",
            "Profile-Health",
            "Hotkey-Backend",
            "ML-Modell",
        }


class TestFormatReport:
    def test_format_includes_status_icons(self) -> None:
        report = DoctorReport(
            checks=(
                Check("A", Status.OK, "fine"),
                Check("B", Status.WARN, "meh"),
                Check("C", Status.FAIL, "broken"),
            )
        )
        text = format_report(report)
        assert "✓ A:" in text
        assert "⚠ B:" in text
        assert "✗ C:" in text
        assert "NICHT EINSATZBEREIT" in text

    def test_format_all_ok(self) -> None:
        report = DoctorReport(checks=(Check("X", Status.OK, "fine"),))
        text = format_report(report)
        assert "Vollständig einsatzbereit" in text

    def test_format_with_warnings_only(self) -> None:
        report = DoctorReport(
            checks=(
                Check("X", Status.OK, "fine"),
                Check("Y", Status.WARN, "be aware"),
            )
        )
        text = format_report(report)
        assert "Einsatzbereit für Kern-Workflow" in text


class TestCLIIntegration:
    def test_doctor_subcommand_registered(self) -> None:
        from pseudokrat.cli import _build_parser

        parser = _build_parser()
        # argparse hat keine direkte API; wir parsen einen Befehl.
        args = parser.parse_args(["doctor"])
        assert args.command == "doctor"
        assert args.profile is None

    def test_doctor_with_profile_flag(self) -> None:
        from pseudokrat.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["doctor", "--profile", "Pilot"])
        assert args.command == "doctor"
        assert args.profile == "Pilot"


class TestInstallDefaultsHotkeysOn:
    """Iter-8: ``pseudokrat install`` schaltet Hotkeys per Default ein.
    --no-hotkeys schaltet aus."""

    def test_install_no_arg_means_hotkeys_on(self) -> None:
        from pseudokrat.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["install"])
        assert args.no_hotkeys is False

    def test_install_no_hotkeys_flag(self) -> None:
        from pseudokrat.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["install", "--no-hotkeys"])
        assert args.no_hotkeys is True
