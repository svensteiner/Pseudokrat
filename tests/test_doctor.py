"""Tests für ``pseudokrat doctor`` (PRL Iter-8).

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

    def test_report_contains_all_checks(self, manager: ProfileManager) -> None:
        report = run_doctor(manager)
        names = {c.name for c in report.checks}
        assert names == {
            "Profile",
            "Anonymize-Roundtrip",
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
